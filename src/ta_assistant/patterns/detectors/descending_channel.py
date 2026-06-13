"""Descending channel (bearish warning): parallel falling rails; downtrend context."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import (
    BEARISH,
    PatternCandidate,
    classify_bearish,
    fit_rails,
)

PATTERN_TYPE = "descending_channel"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    rails = fit_rails(ctx)
    if rails is None:
        return []
    upper, lower, highs, lows, rstart, rend = rails
    if not (upper.slope < 0 and lower.slope < 0):
        return []
    if abs(upper.slope - lower.slope) > 0.3 * abs(lower.slope):
        return []

    breakdown = lower.value_at(rend)
    width = upper.value_at(rend) - lower.value_at(rend)
    if width <= 0 or breakdown <= 0:
        return []
    stop = upper.value_at(rend) + 0.5 * ctx.atr_at(rend)
    status, breakdown_idx = classify_bearish(ctx, rend, breakdown, stop, ctx.pivots[-1].provisional)
    return [
        PatternCandidate(
            pattern_type=PATTERN_TYPE,
            timeframe=ctx.timeframe,
            status=status,
            geometry_confidence=0.55,
            pivots=[*lows, *highs],
            levels={
                "breakout": breakdown,
                "target": breakdown - width,
                "stop": stop,
                "pattern_height": width,
                "neckline_slope": lower.slope,
                "neckline_intercept": lower.intercept,
            },
            region_start_idx=rstart,
            region_end_idx=rend,
            breakout_idx=breakdown_idx,
            direction=BEARISH,
        )
    ]
