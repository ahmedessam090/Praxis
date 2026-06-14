"""LLM mood synthesis for the regime read — the "mixture": deterministic rules produce
the metric facts + a baseline verdict, and the LLM integrates the whole picture into the
final mood. Routed through the `LLMAnalyst.synthesize` abstraction, so it follows whichever
provider is active and falls back to the deterministic verdict when there's no key / the
LLM output can't be parsed or validated.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from ta_assistant.analyst.prompts import REGIME_SYSTEM
from ta_assistant.analyst.provider import LLMAnalyst
from ta_assistant.regime.pillars import Verdict
from ta_assistant.synthesis.schema import LongPosture, RegimePillar, RegimeState

logger = logging.getLogger(__name__)


class RegimeRead(BaseModel):
    """The integrated mood read — pydantic so it round-trips through the LlmCache."""

    state: RegimeState
    posture: LongPosture
    mood: str
    narrative: str
    source: str  # "llm" | "deterministic"


def build_digest(pillars: list[RegimePillar], verdict: Verdict) -> str:
    """Compact, LLM-readable digest of every metric + the deterministic baseline."""
    lines = ["MARKET REGIME — METRIC DIGEST", ""]
    for p in pillars:
        lines.append(f"## {p.name}  [{p.status.value}, score {p.score:+.2f}]")
        for m in p.metrics:
            lines.append(
                f"- {m.label}: {m.value}  [{m.status.value}]  ({m.source_tag})"
                + (f" — {m.detail}" if m.detail else "")
            )
        lines.append("")
    lines.append("## Deterministic baseline verdict")
    lines.append(
        f"- state={verdict.state.value}; posture={verdict.posture.value}; "
        f"mood='{verdict.mood}'; score={verdict.score:+.2f}"
    )
    for k, v in verdict.signals.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def _norm(s: str) -> str:
    return s.strip().lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def _coerce_state(s: str) -> RegimeState | None:
    n = _norm(s)
    for st in RegimeState:
        if n == st.value:
            return st
    return None


def _coerce_posture(s: str) -> LongPosture | None:
    n = _norm(s)
    for ps in LongPosture:
        if n == ps.value:
            return ps
    return None


def _parse(raw: str) -> RegimeRead | None:
    txt = raw.strip()
    if "{" not in txt or "}" not in txt:
        return None
    try:
        data = json.loads(txt[txt.index("{") : txt.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    state = _coerce_state(str(data.get("overall_state", "")))
    posture = _coerce_posture(str(data.get("long_posture", "")))
    narrative = str(data.get("narrative", "")).strip()
    mood = str(data.get("mood", "")).strip()
    if state is None or posture is None or not narrative:
        return None
    return RegimeRead(state=state, posture=posture, mood=mood, narrative=narrative, source="llm")


def synthesize_regime_read(
    pillars: list[RegimePillar], verdict: Verdict, analyst: LLMAnalyst
) -> RegimeRead:
    """Ask the LLM to integrate the metrics into the mood; fall back to the deterministic
    verdict on empty/unparseable/invalid output (so the read is never dark)."""
    raw = ""
    try:
        raw = analyst.synthesize(REGIME_SYSTEM, build_digest(pillars, verdict))
    except Exception as exc:  # noqa: BLE001 - defensive: any analyst error -> fallback
        logger.warning("regime synthesize raised: %s", exc)
    if raw:
        parsed = _parse(raw)
        if parsed is not None:
            return parsed
        logger.warning("regime LLM output unparseable/invalid; using deterministic verdict")
    return RegimeRead(
        state=verdict.state,
        posture=verdict.posture,
        mood=verdict.mood,
        narrative=verdict.narrative,
        source="deterministic",
    )
