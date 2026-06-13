"""Falling wedge (bullish): both rails slope down, resistance falling faster; long the break up."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import PatternCandidate, classify, fit_rails

PATTERN_TYPE = "falling_wedge"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    rails = fit_rails(ctx)
    if rails is None:
        return []
    upper, lower, highs, lows, rstart, rend = rails
    # both down, converging, resistance steeper than support (the bullish tell)
    if not (upper.slope < 0 and lower.slope < 0 and abs(upper.slope) > abs(lower.slope)):
        return []
    if upper.value_at(rstart) - lower.value_at(rstart) <= upper.value_at(rend) - lower.value_at(
        rend
    ):
        return []

    breakout = upper.value_at(rend)
    height = upper.value_at(rstart) - lower.value_at(rstart)  # wedge mouth
    if height <= 0:
        return []
    stop = lower.value_at(rend) - 0.5 * ctx.atr_at(rend)
    status, breakout_idx = classify(ctx, rend, breakout, stop, ctx.pivots[-1].provisional)
    return [
        PatternCandidate(
            pattern_type=PATTERN_TYPE,
            timeframe=ctx.timeframe,
            status=status,
            geometry_confidence=0.6,
            pivots=[*lows, *highs],
            levels={
                "breakout": breakout,
                "target": breakout + height,
                "stop": stop,
                "pattern_height": height,
                "neckline_slope": upper.slope,
                "neckline_intercept": upper.intercept,
            },
            region_start_idx=rstart,
            region_end_idx=rend,
            breakout_idx=breakout_idx,
        )
    ]
