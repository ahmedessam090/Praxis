"""Shared types + helpers for pattern detectors."""

from __future__ import annotations

from dataclasses import dataclass, field

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.types import Pivot

FORMING = "forming"
CONFIRMED = "confirmed"
TRIGGERED = "triggered"
INVALIDATED = "invalidated"


@dataclass
class PatternCandidate:
    """Deterministic (pre-LLM) detection with exact levels."""

    pattern_type: str
    timeframe: str
    status: str
    geometry_confidence: float
    pivots: list[Pivot]
    levels: dict[str, float]
    region_start_idx: int
    region_end_idx: int
    breakout_idx: int | None = None
    prior_resistance: list[float] = field(default_factory=list)
    volume: dict[str, float] = field(default_factory=dict)
    notes: str = ""


def find_breakout_idx(ctx: GeometryContext, after_idx: int, level: float) -> int | None:
    """First bar after `after_idx` whose close exceeds `level` (the trigger)."""
    closes = ctx.df["close"].to_numpy(dtype=float)
    for i in range(int(after_idx) + 1, len(closes)):
        if closes[i] > level:
            return i
    return None


def classify(
    ctx: GeometryContext,
    region_end_idx: int,
    breakout: float,
    stop: float,
    uses_provisional: bool,
) -> tuple[str, int | None]:
    """Deterministic status. Triggered if a later close cleared the breakout;
    invalidated if the last close is below the stop; else confirmed/forming."""
    closes = ctx.df["close"].to_numpy(dtype=float)
    breakout_idx = find_breakout_idx(ctx, region_end_idx, breakout)
    if breakout_idx is not None:
        return TRIGGERED, breakout_idx
    if closes[-1] < stop:
        return INVALIDATED, None
    return (FORMING if uses_provisional else CONFIRMED), None


def closeness_conf(a: float, b: float, tol: float) -> float:
    """1.0 when equal, decaying to ~0.5 at the tolerance edge."""
    if tol <= 0:
        return 0.5
    return max(0.0, min(1.0, 1.0 - 0.5 * abs(a - b) / tol))


def add_volume_features(ctx: GeometryContext, cand: PatternCandidate) -> None:
    from ta_assistant.patterns.volume import breakout_volume_ratio, is_drying_up, obv_slope

    end = min(cand.region_end_idx, len(ctx.df) - 1)
    vol: dict[str, float] = {
        "obv_slope": obv_slope(ctx.df, cand.region_start_idx, end),
        "drying_up": float(is_drying_up(ctx.df, cand.region_start_idx, end)),
    }
    if cand.breakout_idx is not None:
        vol["breakout_volume_ratio"] = breakout_volume_ratio(ctx.df, cand.breakout_idx)
    cand.volume = vol
