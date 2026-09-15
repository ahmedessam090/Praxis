"""Provider-agnostic AI chartist: a bounded vision + tool-use loop that ends when the
model calls `submit_thesis` with levels that pass the deterministic sanity guard.

The loop is the keystone of "AI backed by data": the model proposes a thesis, we validate
its levels with the same `classify_status` guard the engine uses, and on failure we hand
the reason back as a tool result so the model corrects and resubmits.

Two real implementations (Anthropic messages API, OpenAI chat.completions) share the loop
via a Template Method; `NullAnalyst` returns a deterministic thesis from the seed engine
candidates (no key / tests / fallback). SDK imports stay inside methods (Temporal sandbox).
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ta_assistant.analyst.observability import record_llm
from ta_assistant.analyst.prompts import CHARTIST_SYSTEM
from ta_assistant.analyst.tools import ToolContext, build_registry, run_tool
from ta_assistant.config import Settings, get_settings
from ta_assistant.patterns.trendlines import fit_trendline, line_fit_quality
from ta_assistant.synthesis.schema import (
    DetectedPattern,
    PatternStatus,
    PriceNote,
    Shape,
    ShapeKind,
    ShapePoint,
    Timeframe,
    TimeframeThesis,
)

logger = logging.getLogger(__name__)
SUBMIT = "submit_thesis"
# Reasoning models (gpt-5 / Claude) work tool-by-tool and need room to gather evidence
# before submitting; 6 was too tight (they timed out mid-analysis and fell back).
_MAX_TURNS = 16


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    id: str
    content: str


@dataclass
class AnalystResult:
    thesis: TimeframeThesis | None
    source: str  # "llm" | "deterministic" | "error" | "incomplete"
    transcript: list[str] = field(default_factory=list)


# --------------------------- submit_thesis schema ---------------------------

_POINT = {
    "type": "object",
    "properties": {"ts": {"type": "string"}, "price": {"type": "number"}},
    "required": ["ts", "price"],
}
_SHAPE = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": [k.value for k in ShapeKind]},
        "points": {"type": "array", "items": _POINT},
        "label": {"type": "string"},
        "role": {"type": "string"},
    },
    "required": ["kind", "points"],
}
_NOTE = {
    "type": "object",
    "properties": {
        "price": {"type": "number"},
        "label": {"type": "string"},
        "kind": {"type": "string"},
    },
    "required": ["price", "label", "kind"],
}


def _submit_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "pattern_label": {"type": "string", "description": "human pattern name"},
            "status": {
                "type": "string",
                "enum": [s.value for s in PatternStatus],
            },
            "direction": {"type": "string", "enum": ["bullish", "bearish"]},
            "confidence": {"type": "number"},
            "entry": {"type": "number"},
            "breakout": {"type": "number"},
            "target": {"type": "number"},
            "target2": {"type": "number"},
            "stop": {"type": "number"},
            "shapes": {"type": "array", "items": _SHAPE},
            "price_notes": {"type": "array", "items": _NOTE},
            "supporting_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "non-tradeable confirmations: rounding bottom, double/triple "
                "bottom, volume, trend — NOT the core pattern",
            },
            "rationale": {"type": "string"},
        },
        "required": ["pattern_label", "direction", "confidence", "rationale"],
    }


def _tool_defs(registry: list[Any]) -> list[tuple[str, str, dict[str, Any]]]:
    defs = [(t.name, t.description, t.parameters) for t in registry]
    defs.append(
        (
            SUBMIT,
            "Finalise: submit your pattern thesis (levels, shapes to draw, price notes, "
            "rationale). Levels must pass classify_status (levels_sane=true).",
            _submit_schema(),
        )
    )
    return defs


# --------------------------- thesis build + validate ---------------------------


def _validate_levels(
    inp: dict[str, Any], ctx: ToolContext, registry: list[Any]
) -> tuple[bool, str]:
    target = inp.get("target")
    if target is None:
        return True, ""  # a pure forming identification with no firm levels is allowed
    breakout = inp.get("breakout") if inp.get("breakout") is not None else inp.get("entry")
    stop = inp.get("stop")
    if breakout is None or stop is None:
        return False, "provide breakout and stop alongside target so the setup is tradeable"
    res = run_tool(
        registry,
        "classify_status",
        {
            "breakout": breakout,
            "stop": stop,
            "target": target,
            "region_end_ts": ctx.ts_at(len(ctx.df) - 1),
            "direction": inp.get("direction", "bullish"),
        },
        ctx,
    )
    if not res.get("levels_sane"):
        order = (
            "stop < breakout < target"
            if inp.get("direction", "bullish") == "bullish"
            else "target < breakdown < stop"
        )
        return False, (
            f"levels not sane: need {order}, all positive and within band "
            f"{res.get('sane_band')}; revise using tool-measured levels"
        )
    # Validate the EFFECTIVE entry the thesis will use (not just the breakout). This is the hole
    # the MU bug slipped through: a re-break entry above an already-hit target.
    if inp.get("direction", "bullish") == "bullish":
        entry = inp.get("entry") if inp.get("entry") is not None else breakout
        if not (stop < entry < target):
            return False, (
                f"entry {entry} must sit between the stop {stop} and target {target} — use the "
                f"breakout pivot as the entry (an entry above the target is incoherent); revise"
            )
        last_close = float(ctx.df["close"].to_numpy(dtype=float)[-1])
        if target <= last_close:
            return False, (
                f"target {target} is at or below the current price {last_close:.2f} — this move "
                f"has already played out; submit a setup with upside left or identify it as "
                f"forming with no firm target"
            )
    return True, ""


_LINE_ROLES = {"resistance", "support", "neckline"}


def _verify_line_shape(shape: Shape, ctx: ToolContext) -> bool:
    """For a defining-line shape (trendline / neckline / rail), score it against the REAL swing
    pivots: stamp touch_count + fit_residual so the user can match the straight line, and drop a
    line anchored to nothing real (0 touches). Non-line shapes always pass through unchanged."""
    is_line = shape.kind == ShapeKind.TRENDLINE or shape.role in _LINE_ROLES
    if not is_line or len(shape.points) < 2:
        return True
    try:
        line = fit_trendline(
            [ctx.pos(p.ts) for p in shape.points], [p.price for p in shape.points]
        )
    except ValueError:
        return True
    geo = ctx.geo("fine")
    last_close = float(ctx.df["close"].to_numpy(dtype=float)[-1])
    tol = max(0.02 * last_close, 1.5 * geo.atr_at(len(ctx.df) - 1))  # a point or two of slack
    pivots = [*geo.pivots, *ctx.geo("medium").pivots]
    touches, residual = line_fit_quality(line, pivots, tol)
    shape.touch_count = touches
    shape.fit_residual = round(residual, 2) if residual != float("inf") else None
    return touches >= 1  # a line that touches no real swing at all is a phantom — drop it


def _parse_shapes(raw: list[dict[str, Any]], ctx: ToolContext) -> list[Shape]:
    lo = ctx.df.index[0]
    hi = ctx.df.index[-1]
    shapes: list[Shape] = []
    for s in raw or []:
        try:
            kind = ShapeKind(s.get("kind", "hline"))
        except ValueError:
            continue
        points: list[ShapePoint] = []
        for p in s.get("points", []):
            try:
                ts = ctx.df.index[ctx.pos(p["ts"])]  # snap to a real bar
                if ts < lo or ts > hi:
                    continue
                points.append(ShapePoint(ts=ts.to_pydatetime(), price=float(p["price"])))
            except (KeyError, TypeError, ValueError):
                continue
        if not points and kind != ShapeKind.HLINE:
            continue
        shape = Shape(
            kind=kind,
            points=points,
            label=str(s.get("label", "")),
            role=str(s.get("role", "primary")),
        )
        if _verify_line_shape(shape, ctx):  # drop phantom lines; stamp touch_count on real ones
            shapes.append(shape)
    return shapes


def _build_thesis(
    inp: dict[str, Any], ctx: ToolContext, timeframe: Timeframe, transcript: list[str]
) -> TimeframeThesis:
    breakout = inp.get("breakout")
    entry = inp.get("entry") if inp.get("entry") is not None else breakout
    target = inp.get("target")
    stop = inp.get("stop")
    # Repair (belt to _validate_levels' suspenders): if the breakout-based levels are sane but
    # the submitted entry sits outside (stop, target), snap entry to the breakout pivot so the
    # thesis can never carry an incoherent entry/R:R (the MU bug).
    if (
        breakout is not None
        and stop is not None
        and target is not None
        and 0 < stop < breakout < target
        and (entry is None or not (stop < entry < target))
    ):
        entry = breakout
    rr = None
    if entry is not None and stop is not None and target is not None and abs(entry - stop) > 0:
        rr = round((target - entry) / (entry - stop), 2)
    try:
        status = PatternStatus(inp.get("status", "forming"))
    except ValueError:
        status = PatternStatus.FORMING
    notes = [
        PriceNote(
            price=float(n["price"]),
            label=str(n.get("label", "")),
            kind=str(n.get("kind", "level")),
        )
        for n in inp.get("price_notes", [])
        if n.get("price") is not None
    ]
    return TimeframeThesis(
        timeframe=timeframe,
        pattern_label=str(inp.get("pattern_label", "unidentified")),
        status=status,
        direction=str(inp.get("direction", "bullish")),
        confidence=float(inp.get("confidence", 0.5)),
        entry=entry,
        breakout=breakout,
        target=target,
        target2=inp.get("target2"),
        stop=stop,
        rr_ratio=rr,
        shapes=_parse_shapes(inp.get("shapes", []), ctx),
        price_notes=notes,
        supporting_factors=[str(x) for x in inp.get("supporting_factors", []) if x][:5],
        rationale=str(inp.get("rationale", "")),
        transcript=transcript[:],
        source="llm",
    )


def _fmt_call(c: ToolCall) -> str:
    args = ", ".join(f"{k}={v}" for k, v in list(c.input.items())[:3]) if c.input else ""
    return f"{c.name}({args[:80]})"


# --------------------------- deterministic fallback ---------------------------


def _level_notes(
    entry: float | None, target: float | None, stop: float | None, target2: float | None = None
) -> list[PriceNote]:
    """One clean note per DISTINCT trade level (deduped by rounded price) — no stacked tags."""
    out: list[PriceNote] = []
    seen: set[float] = set()
    for v, label, kind in (
        (entry, "Entry / breakout", "breakout"),
        (target, "Target", "target"),
        (target2, "Target 2", "target"),
        (stop, "Stop", "stop"),
    ):
        if v is None:
            continue
        r = round(float(v), 2)
        if r in seen:
            continue
        seen.add(r)
        out.append(PriceNote(price=float(v), label=f"{label} {v:.2f}", kind=kind))
    return out


def _shapes_and_notes(p: DetectedPattern) -> tuple[list[Shape], list[PriceNote]]:
    """Textbook geometry + clean level notes from a deterministic candidate. (Inverse) H&S
    gets a neckline rail + an arc and LS/Head/RS markers in the CORRECT order (the head is
    the central, lowest trough); other patterns get clean resistance/support rails."""
    shapes: list[Shape] = []
    highs = [pv for pv in p.pivots if pv.kind == "H"]
    lows = [pv for pv in p.pivots if pv.kind == "L"]
    is_hns = "head_and_shoulders" in p.pattern_type and len(p.pivots) == 5
    if "neckline_slope" in p.levels and "neckline_intercept" in p.levels:
        sl, ic = p.levels["neckline_slope"], p.levels["neckline_intercept"]
        shapes.append(
            Shape(
                kind=ShapeKind.TRENDLINE,
                points=[
                    ShapePoint(ts=p.region_start, price=sl * p.region_start_idx + ic),
                    ShapePoint(ts=p.region_end, price=sl * p.region_end_idx + ic),
                ],
                role="neckline",
                label="neckline",
            )
        )
    else:
        if len(highs) >= 2:
            shapes.append(
                Shape(
                    kind=ShapeKind.TRENDLINE,
                    points=[
                        ShapePoint(ts=highs[0].ts, price=highs[0].price),
                        ShapePoint(ts=highs[-1].ts, price=highs[-1].price),
                    ],
                    role="resistance",
                    label="resistance",
                )
            )
        if len(lows) >= 2:
            shapes.append(
                Shape(
                    kind=ShapeKind.TRENDLINE,
                    points=[
                        ShapePoint(ts=lows[0].ts, price=lows[0].price),
                        ShapePoint(ts=lows[-1].ts, price=lows[-1].price),
                    ],
                    role="support",
                    label="support",
                )
            )
    if is_hns:
        # detector pivots are L,H,L,H,L -> troughs 0,2,4 = LS, Head, RS in textbook order
        ls, head, rs = p.pivots[0], p.pivots[2], p.pivots[4]
        shapes.append(
            Shape(
                kind=ShapeKind.CURVE,
                points=[
                    ShapePoint(ts=ls.ts, price=ls.price),
                    ShapePoint(ts=head.ts, price=head.price),
                    ShapePoint(ts=rs.ts, price=rs.price),
                ],
                role="primary",
                label="",
            )
        )
        for piv, lbl in ((ls, "LS"), (head, "Head"), (rs, "RS")):
            shapes.append(
                Shape(
                    kind=ShapeKind.MARKER,
                    points=[ShapePoint(ts=piv.ts, price=piv.price)],
                    role="primary",
                    label=lbl,
                )
            )
    return shapes, _level_notes(p.entry, p.target, p.stop)


# label keyword -> deterministic detector type (for snapping the drawing to textbook geometry)
_SEED_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (
        ("inverse head", "head and shoulders bottom", "head-and-shoulders bottom",
         "h&s bottom", "inverse h&s"),
        "head_and_shoulders_bottom",
    ),
    (("head and shoulders top", "h&s top"), "head_and_shoulders_top"),
    (("ascending triangle",), "ascending_triangle"),
    (("descending triangle",), "descending_triangle"),
    (("symmetrical triangle",), "symmetrical_triangle"),
    (("cup",), "cup_and_handle"),
    (("triple bottom",), "triple_bottom"),
    (("double bottom",), "double_bottom"),
    (("falling wedge",), "falling_wedge"),
    (("ascending channel",), "ascending_channel"),
    (("rectangle", "range", "box"), "rectangle"),
    (("bull flag", "flag", "pennant"), "bull_flag"),
]


def _attach_support(thesis: TimeframeThesis, seeds: list[DetectedPattern]) -> TimeframeThesis:
    """Surface SUPPORT-tier structures (rounding/double/triple bottom) as the supporting
    STORY: list them in supporting_factors and draw the rounding-bottom saucer faintly
    behind the core pattern. They strengthen the setup; they are never the trade."""
    for s in sorted(
        (x for x in seeds if x.tier == "support"), key=lambda x: x.confidence, reverse=True
    ):
        label = s.pattern_type.replace("_", " ")
        if label not in thesis.supporting_factors:
            thesis.supporting_factors.append(label)
        if s.pattern_type == "rounding_bottom" and len(s.pivots) >= 3:
            if not any(sh.label == "rounding bottom" for sh in thesis.shapes):
                thesis.shapes.append(
                    Shape(
                        kind=ShapeKind.CURVE,
                        points=[ShapePoint(ts=pv.ts, price=pv.price) for pv in s.pivots],
                        role="context",
                        label="rounding bottom",
                    )
                )
    thesis.supporting_factors = thesis.supporting_factors[:5]
    return thesis


def _match_seed(label: str, seeds: list[DetectedPattern]) -> DetectedPattern | None:
    low = label.lower()
    for keys, ptype in _SEED_KEYWORDS:
        if any(k in low for k in keys):
            cands = [s for s in seeds if s.pattern_type == ptype]
            if cands:
                return max(cands, key=lambda s: s.confidence)
    return None


def textbookize(thesis: TimeframeThesis, seeds: list[DetectedPattern]) -> TimeframeThesis:
    """When the analyst's label matches a deterministic candidate, SNAP the drawing + levels
    to the engine's textbook geometry (correct LS/Head/RS order, clean rails, exact levels)
    while keeping the analyst's label/rationale/confidence — so patterns are textbook and the
    price tags stay clean. Otherwise, just rebuild minimal deduped notes from its levels."""
    seed = _match_seed(thesis.pattern_label, seeds)
    if seed is not None:
        context = [s for s in thesis.shapes if s.role == "context"]  # keep the analyst's saucer
        thesis.shapes, thesis.price_notes = _shapes_and_notes(seed)
        thesis.shapes.extend(context)
        thesis.entry = seed.entry
        thesis.breakout = seed.entry
        thesis.target = seed.target
        thesis.stop = seed.stop
        thesis.rr_ratio = seed.rr_ratio
        thesis.status = seed.status
        thesis.seed_pattern_ids = [seed.id]
    else:
        thesis.price_notes = _level_notes(
            thesis.entry or thesis.breakout, thesis.target, thesis.stop, thesis.target2
        )
        # Keep R:R consistent with the (possibly repaired) entry — never leave it stale.
        e, t, s = thesis.entry, thesis.target, thesis.stop
        if e is not None and t is not None and s is not None and abs(e - s) > 0:
            thesis.rr_ratio = round((t - e) / (e - s), 2)
    return _attach_support(thesis, seeds)


def deterministic_thesis(timeframe: Timeframe, seeds: list[DetectedPattern]) -> TimeframeThesis:
    """Build a thesis from the seed engine candidates (consensus roles already assigned).
    Used with no key, on LLM failure, or when a proposed thesis fails sanity."""
    bulls = [p for p in seeds if p.direction == "bullish"]
    primary = next((p for p in seeds if p.role == "primary"), None)
    if primary is None and bulls:
        primary = max(bulls, key=lambda p: p.confidence)
    if primary is None:
        # no core trade — but a support structure (rounding/double bottom) may still be the story
        empty = TimeframeThesis(
            timeframe=timeframe,
            pattern_label="no clean long setup",
            status=PatternStatus.FORMING,
            confidence=0.0,
            rationale="The deterministic engine found no currently-actionable core setup.",
            source="deterministic",
        )
        return _attach_support(empty, seeds)
    p = primary
    shapes, notes = _shapes_and_notes(p)
    thesis = TimeframeThesis(
        timeframe=timeframe,
        pattern_label=p.display_label,
        status=p.status,
        direction=p.direction,
        confidence=p.confidence,
        entry=p.entry,
        breakout=p.entry,
        target=p.target,
        stop=p.stop,
        rr_ratio=p.rr_ratio,
        shapes=shapes,
        price_notes=notes,
        rationale=(p.caution or f"{p.display_label} ({p.status.value}) — deterministic read."),
        source="deterministic",
        seed_pattern_ids=[p.id],
    )
    return _attach_support(thesis, seeds)


# --------------------------------- analysts ---------------------------------


class LLMAnalyst(Protocol):
    def run_thesis_loop(
        self,
        *,
        user_text: str,
        image_paths: list[str],
        tool_ctx: ToolContext,
        timeframe: Timeframe,
        max_turns: int = _MAX_TURNS,
    ) -> AnalystResult: ...

    def synthesize(self, system: str, user: str) -> str:
        """One-shot, no-tool/no-vision text completion (e.g. the Market Regime mood
        narrative). Returns "" on no key / SDK failure so callers use their deterministic
        fallback. Routed through the same provider abstraction so it follows whichever
        provider is active."""
        ...


class _BaseAnalyst:
    """Shared bounded loop. Subclasses implement the 4 provider-specific primitives."""

    system: str = CHARTIST_SYSTEM

    def run_thesis_loop(
        self,
        *,
        user_text: str,
        image_paths: list[str],
        tool_ctx: ToolContext,
        timeframe: Timeframe,
        max_turns: int = _MAX_TURNS,
    ) -> AnalystResult:
        registry = build_registry()
        tools = self._render_tools(registry)
        messages = self._init_messages(user_text, image_paths)
        transcript: list[str] = []
        for _ in range(max_turns):
            try:
                resp = self._call(messages, tools)
            except Exception as exc:  # noqa: BLE001 - any SDK/network error -> fallback
                logger.warning("analyst call failed: %s", exc)
                return AnalystResult(thesis=None, source="error", transcript=transcript)
            calls = self._extract_tool_calls(resp)
            if not calls:
                break  # model stopped without submitting -> fall back
            self._append_assistant(messages, resp)
            results: list[ToolResult] = []
            for c in calls:
                transcript.append(_fmt_call(c))
                if c.name == SUBMIT:
                    ok, reason = _validate_levels(c.input, tool_ctx, registry)
                    if ok:
                        thesis = _build_thesis(c.input, tool_ctx, timeframe, transcript)
                        return AnalystResult(thesis=thesis, source="llm", transcript=transcript)
                    results.append(
                        ToolResult(c.id, json.dumps({"accepted": False, "error": reason}))
                    )
                else:
                    results.append(
                        ToolResult(c.id, json.dumps(run_tool(registry, c.name, c.input, tool_ctx)))
                    )
            self._append_tool_results(messages, results)
        return AnalystResult(thesis=None, source="incomplete", transcript=transcript)

    # provider primitives (implemented per provider) ---------------------------
    def _render_tools(self, registry: list[Any]) -> Any:
        raise NotImplementedError

    def _init_messages(self, user_text: str, image_paths: list[str]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _call(self, messages: list[dict[str, Any]], tools: Any) -> Any:
        raise NotImplementedError

    def _extract_tool_calls(self, resp: Any) -> list[ToolCall]:
        raise NotImplementedError

    def _append_assistant(self, messages: list[dict[str, Any]], resp: Any) -> None:
        raise NotImplementedError

    def _append_tool_results(
        self, messages: list[dict[str, Any]], results: list[ToolResult]
    ) -> None:
        raise NotImplementedError


def _b64(path: str) -> str:
    return base64.standard_b64encode(Path(path).read_bytes()).decode()


class AnthropicAnalyst(_BaseAnalyst):
    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key, self._model, self._client = api_key, model, client

    def _client_(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _render_tools(self, registry: list[Any]) -> Any:
        return [
            {"name": n, "description": d, "input_schema": s} for n, d, s in _tool_defs(registry)
        ]

    def _init_messages(self, user_text: str, image_paths: list[str]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": _b64(p)},
            }
            for p in image_paths
            if Path(p).exists()
        ]
        content.append({"type": "text", "text": user_text})
        return [{"role": "user", "content": content}]

    def _call(self, messages: list[dict[str, Any]], tools: Any) -> Any:
        resp = self._client_().messages.create(
            model=self._model,
            max_tokens=4096,
            system=self.system,
            messages=messages,
            tools=tools,
        )
        record_llm(
            name="chartist.turn",
            provider="anthropic",
            model=self._model,
            resp=resp,
            input={"turn": "vision+tools", "messages": len(messages)},
        )
        return resp

    def synthesize(self, system: str, user: str) -> str:
        try:
            resp = self._client_().messages.create(
                model=self._model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            record_llm(
                name="regime.mood",
                provider="anthropic",
                model=self._model,
                resp=resp,
                input=user,
                output=text,
            )
            return text
        except Exception as exc:  # noqa: BLE001 - any SDK/network error -> deterministic fallback
            logger.warning("regime synthesize (anthropic) failed: %s", exc)
            return ""

    def _extract_tool_calls(self, resp: Any) -> list[ToolCall]:
        return [
            ToolCall(id=b.id, name=b.name, input=dict(b.input or {}))
            for b in resp.content
            if getattr(b, "type", None) == "tool_use"
        ]

    def _append_assistant(self, messages: list[dict[str, Any]], resp: Any) -> None:
        messages.append({"role": "assistant", "content": resp.content})

    def _append_tool_results(
        self, messages: list[dict[str, Any]], results: list[ToolResult]
    ) -> None:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": r.id, "content": r.content}
                    for r in results
                ],
            }
        )


class OpenAIAnalyst(_BaseAnalyst):
    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key, self._model, self._client = api_key, model, client

    def _client_(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def _render_tools(self, registry: list[Any]) -> Any:
        return [
            {"type": "function", "function": {"name": n, "description": d, "parameters": s}}
            for n, d, s in _tool_defs(registry)
        ]

    def _init_messages(self, user_text: str, image_paths: list[str]) -> list[dict[str, Any]]:
        user: list[dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64(p)}"}}
            for p in image_paths
            if Path(p).exists()
        ]
        user.append({"type": "text", "text": user_text})
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": user},
        ]

    def _call(self, messages: list[dict[str, Any]], tools: Any) -> Any:
        kwargs: dict[str, Any] = {"model": self._model, "messages": messages, "tools": tools}
        # gpt-5 / o-series reasoning models reject a custom temperature; only gpt-4* take it.
        if self._model.lower().startswith("gpt-4"):
            kwargs["temperature"] = 0
        resp = self._client_().chat.completions.create(**kwargs)
        record_llm(
            name="chartist.turn",
            provider="openai",
            model=self._model,
            resp=resp,
            input={"turn": "vision+tools", "messages": len(messages)},
        )
        return resp

    def synthesize(self, system: str, user: str) -> str:
        try:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            if self._model.lower().startswith("gpt-4"):
                kwargs["temperature"] = 0
            resp = self._client_().chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            record_llm(
                name="regime.mood",
                provider="openai",
                model=self._model,
                resp=resp,
                input=user,
                output=text,
            )
            return text
        except Exception as exc:  # noqa: BLE001 - any SDK/network error -> deterministic fallback
            logger.warning("regime synthesize (openai) failed: %s", exc)
            return ""

    def _extract_tool_calls(self, resp: Any) -> list[ToolCall]:
        msg = resp.choices[0].message
        out: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            out.append(ToolCall(id=tc.id, name=tc.function.name, input=args))
        return out

    def _append_assistant(self, messages: list[dict[str, Any]], resp: Any) -> None:
        msg = resp.choices[0].message
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in (msg.tool_calls or [])
                ],
            }
        )

    def _append_tool_results(
        self, messages: list[dict[str, Any]], results: list[ToolResult]
    ) -> None:
        for r in results:
            messages.append({"role": "tool", "tool_call_id": r.id, "content": r.content})


class NullAnalyst:
    """Deterministic analyst: thesis straight from the seed engine candidates (no key)."""

    def run_thesis_loop(
        self,
        *,
        user_text: str,
        image_paths: list[str],
        tool_ctx: ToolContext,
        timeframe: Timeframe,
        max_turns: int = _MAX_TURNS,
    ) -> AnalystResult:
        return AnalystResult(
            thesis=deterministic_thesis(timeframe, tool_ctx.seeds), source="deterministic"
        )

    def synthesize(self, system: str, user: str) -> str:
        return ""  # no key -> caller uses its deterministic narrative


def get_analyst(settings: Settings | None = None) -> LLMAnalyst:
    s = settings or get_settings()
    if s.active_provider == "anthropic" and s.anthropic_api_key:
        return AnthropicAnalyst(s.anthropic_api_key, s.anthropic_model)
    if s.active_provider == "openai" and s.openai_api_key:
        return OpenAIAnalyst(s.openai_api_key, s.openai_model)
    return NullAnalyst()
