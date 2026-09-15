"""agent: judge whether a CHOSEN chart pattern actually makes sense and is tradeable now.

The LLM vets the surfaced setup — does the labeled pattern legitimately match the price
structure (clean lines, enough real touches), is it FORMED (not still forming), is it actionable
now or on a defined break, or has it already played out? An illegitimate setup is demoted
(action_state -> invalid) so it can't drive the alpha decision. The deterministic action-state
gates are the floor + the no-key fallback. Mirrors the regime/alpha LLM pattern.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from ta_assistant.analyst.prompts import JUDGE_SYSTEM
from ta_assistant.analyst.provider import LLMAnalyst
from ta_assistant.patterns.action_state import ActionState, normalize_state
from ta_assistant.synthesis.schema import TickerAnalysis, TimeframeThesis

logger = logging.getLogger(__name__)

_TRADEABLE = {
    ActionState.IN_RANGE.value,
    ActionState.AWAITING_BREAK.value,
    ActionState.EXTENDED.value,
}


class PatternJudgment(BaseModel):
    """Whether a surfaced setup is a legitimate, currently-actionable pattern."""

    symbol: str
    timeframe: str
    valid: bool = True
    action_state: str = ""
    reason: str = ""
    source: str = "deterministic"  # "llm" | "deterministic"


def _best_bull(analysis: TickerAnalysis) -> TimeframeThesis | None:
    """The thesis the alpha gate would surface — prefer a tradeable one, then by confidence."""
    bulls = [t for t in analysis.theses if t.direction == "bullish"]
    if not bulls:
        return None
    return max(bulls, key=lambda t: (normalize_state(t.action_state) in _TRADEABLE, t.confidence))


def deterministic_judgment(thesis: TimeframeThesis, symbol: str) -> PatternJudgment:
    """No-LLM floor: a setup is valid iff its (deterministic) action-state has a live trigger."""
    state = normalize_state(thesis.action_state)
    valid = state in _TRADEABLE
    reason = f"{thesis.pattern_label}: state={state or 'n/a'}" + (
        "" if valid else " — no formed structure with a live trigger"
    )
    return PatternJudgment(
        symbol=symbol,
        timeframe=thesis.timeframe.value,
        valid=valid,
        action_state=thesis.action_state,
        reason=reason,
        source="deterministic",
    )


def _digest(analysis: TickerAnalysis, thesis: TimeframeThesis) -> str:
    lines = [
        f"PATTERN CHECK — {analysis.symbol} {thesis.timeframe.value}",
        f"Labeled: {thesis.pattern_label} (status={thesis.status.value}, "
        f"state={thesis.action_state or 'n/a'})",
        f"Levels: entry={thesis.entry} breakout={thesis.breakout} target={thesis.target} "
        f"stop={thesis.stop} rr={thesis.rr_ratio}; last price {analysis.summary.price_now:.2f}",
    ]
    if thesis.trigger_zone_low is not None and thesis.trigger_zone_high is not None:
        lines.append(
            f"Trigger range: {thesis.trigger_zone_low:.2f}-{thesis.trigger_zone_high:.2f}"
        )
    lines.append("Defining lines (touches against real swings):")
    line_shapes = [s for s in thesis.shapes if s.touch_count is not None]
    if line_shapes:
        for s in line_shapes:
            lines.append(
                f"- {s.role or s.kind.value} '{s.label}': {s.touch_count} touches, "
                f"residual {s.fit_residual}"
            )
    else:
        lines.append("- (no verified straight-line geometry attached)")
    if thesis.rationale:
        lines.append(f"Analyst rationale: {thesis.rationale}")
    return "\n".join(lines)


def _parse(raw: str, symbol: str, timeframe: str) -> PatternJudgment | None:
    if "{" not in raw or "}" not in raw:
        return None
    try:
        data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "valid" not in data:
        return None
    return PatternJudgment(
        symbol=symbol,
        timeframe=timeframe,
        valid=bool(data.get("valid")),
        action_state=str(data.get("action_state", "")),
        reason=str(data.get("reason", "")).strip(),
        source="llm",
    )


def judge_patterns(analysis: TickerAnalysis, analyst: LLMAnalyst) -> list[PatternJudgment]:
    """Vet the surfaced setup; DEMOTE an illegitimate one (action_state -> invalid) in place so
    it can't drive the alpha decision. Returns the judgment(s) for auditing."""
    thesis = _best_bull(analysis)
    if thesis is None:
        return []
    raw = ""
    try:
        raw = analyst.synthesize(JUDGE_SYSTEM, _digest(analysis, thesis))
    except Exception as exc:  # noqa: BLE001 - never let the judge break the pipeline
        logger.warning("pattern judge synthesize raised: %s", exc)
    judgment = _parse(raw, analysis.symbol, thesis.timeframe.value) if raw else None
    if judgment is None:
        judgment = deterministic_judgment(thesis, analysis.symbol)
    if not judgment.valid:
        thesis.action_state = ActionState.INVALID.value  # demote so the alpha gate skips it
    return [judgment]
