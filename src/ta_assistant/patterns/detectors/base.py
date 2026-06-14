"""Shared types + helpers for pattern detectors."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.types import Pivot

FORMING = "forming"
CONFIRMED = "confirmed"
TRIGGERED = "triggered"
INVALIDATED = "invalidated"

BULLISH = "bullish"
BEARISH = "bearish"

# Pattern tier (classical charting): CORE = a tradeable setup that defines entry/target/stop;
# SUPPORT = context that strengthens a core setup or tells the big-picture story (rounding
# bottom, double/triple bottom) but is not traded on its own.
CORE = "core"
SUPPORT = "support"

# Level keys that are NOT prices (deltas / line params) — exempt from band checks.
_NON_PRICE_LEVEL_KEYS = {
    "pattern_height",
    "neckline_slope",
    "neckline_intercept",
    "parabola_a",
    "parabola_b",
    "parabola_c",
}


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
    direction: str = BULLISH
    conflicts_with: list[str] = field(default_factory=list)
    tier: str = CORE  # CORE (tradeable) | SUPPORT (context/confirmation)


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


def fit_rails(ctx: GeometryContext, n: int = 4) -> tuple | None:  # type: ignore[type-arg]
    """Fit an upper line through recent swing highs and a lower line through recent
    swing lows. Shared by the triangle / wedge / channel detectors. Returns
    (upper, lower, highs, lows, region_start_idx, region_end_idx) or None."""
    from ta_assistant.patterns.trendlines import fit_trendline

    # Exclude the provisional last pivot (often the breakout itself) so it can't
    # pollute the rail fit.
    highs = [p for p in ctx.pivots if p.kind == "H" and not p.provisional][-n:]
    lows = [p for p in ctx.pivots if p.kind == "L" and not p.provisional][-n:]
    if len(highs) < 2 or len(lows) < 2:
        return None
    upper = fit_trendline([p.idx for p in highs], [p.price for p in highs])
    lower = fit_trendline([p.idx for p in lows], [p.price for p in lows])
    region_start = min(highs[0].idx, lows[0].idx)
    region_end = max(highs[-1].idx, lows[-1].idx)
    return upper, lower, highs, lows, region_start, region_end


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


def find_breakdown_idx(ctx: GeometryContext, after_idx: int, level: float) -> int | None:
    """First bar after `after_idx` whose close drops below `level` (bearish trigger)."""
    closes = ctx.df["close"].to_numpy(dtype=float)
    for i in range(int(after_idx) + 1, len(closes)):
        if closes[i] < level:
            return i
    return None


def classify_bearish(
    ctx: GeometryContext,
    region_end_idx: int,
    breakdown: float,
    invalidation: float,
    uses_provisional: bool,
) -> tuple[str, int | None]:
    """Bearish mirror of `classify`: triggered on a close below the breakdown level;
    invalidated if the last close popped back above the structure (top failed)."""
    closes = ctx.df["close"].to_numpy(dtype=float)
    breakdown_idx = find_breakdown_idx(ctx, region_end_idx, breakdown)
    if breakdown_idx is not None:
        return TRIGGERED, breakdown_idx
    if closes[-1] > invalidation:
        return INVALIDATED, None
    return (FORMING if uses_provisional else CONFIRMED), None


def sane_levels(cand: PatternCandidate, last_close: float) -> bool:
    """Reject candidates with degenerate/absurd levels (the root-cause guard for the
    negative-axis bug). All price-like levels must be finite, > 0, within a sane
    multiplicative band of the current price, correctly ordered, with a plausible
    measured move and (bullish) risk/reward."""
    if last_close <= 0:
        return False
    levels = cand.levels
    breakout, target, stop = levels.get("breakout"), levels.get("target"), levels.get("stop")
    height = levels.get("pattern_height")
    if breakout is None or target is None or stop is None or height is None:
        return False
    if not all(math.isfinite(v) for v in levels.values()):
        return False

    lo, hi = 0.25 * last_close, 3.0 * last_close
    for key, value in levels.items():
        if key in _NON_PRICE_LEVEL_KEYS:
            continue
        if not (lo <= value <= hi):  # also enforces value > 0 since lo > 0
            return False

    if cand.direction == BULLISH:
        if not (0 < stop < breakout < target):
            return False
        risk = breakout - stop
        if risk <= 0 or not (0.3 <= (target - breakout) / risk <= 12.0):
            return False
    else:  # bearish: target (down) < breakdown < invalidation stop
        if not (0 < target < breakout < stop):
            return False

    return 0.02 * last_close <= height <= 1.5 * last_close


def is_actionable(cand: PatternCandidate, last_close: float, recent_cutoff: int) -> bool:
    """Keep only currently-tradeable patterns: forming, confirmed (awaiting break), or
    just-triggered-but-not-yet-at-target. Drop invalidated, stale, or played-out."""
    if cand.status == INVALIDATED or cand.region_end_idx < recent_cutoff:
        return False
    breakout, target = cand.levels.get("breakout"), cand.levels.get("target")
    if breakout is None or target is None:
        return False

    if cand.direction == BULLISH:
        if cand.status == TRIGGERED:
            recent = cand.breakout_idx is not None and cand.breakout_idx >= recent_cutoff
            return recent and breakout < last_close < target  # broke out, not yet at target
        return last_close < target  # forming/confirmed: not already run past target
    # bearish warning
    if cand.status == TRIGGERED:
        recent = cand.breakout_idx is not None and cand.breakout_idx >= recent_cutoff
        return recent and target < last_close < breakout
    return last_close > target  # forming/confirmed top: not already fully played out
