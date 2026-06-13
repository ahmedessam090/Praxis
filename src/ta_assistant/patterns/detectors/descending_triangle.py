"""Descending triangle (bearish warning): flat support + falling highs; warns of a breakdown."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import (
    BEARISH,
    PatternCandidate,
    classify_bearish,
    fit_rails,
)

PATTERN_TYPE = "descending_triangle"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    rails = fit_rails(ctx)
    if rails is None:
        return []
    upper, lower, highs, lows, rstart, rend = rails
    if upper.slope >= 0:
        return []
    if abs(lower.slope) > 0.3 * abs(upper.slope):  # support must be ~flat
        return []

    breakdown = lower.value_at(rend)
    height = upper.value_at(rstart) - lower.value_at(rstart)
    if height <= 0 or breakdown <= 0:
        return []
    stop = upper.value_at(rstart) + 0.5 * ctx.atr_at(rend)
    status, breakdown_idx = classify_bearish(ctx, rend, breakdown, stop, ctx.pivots[-1].provisional)
    return [
        PatternCandidate(
            pattern_type=PATTERN_TYPE,
            timeframe=ctx.timeframe,
            status=status,
            geometry_confidence=0.6,
            pivots=[*lows, *highs],
            levels={
                "breakout": breakdown,
                "support": breakdown,
                "target": breakdown - height,
                "stop": stop,
                "pattern_height": height,
                "neckline_slope": lower.slope,
                "neckline_intercept": lower.intercept,
            },
            region_start_idx=rstart,
            region_end_idx=rend,
            breakout_idx=breakdown_idx,
            direction=BEARISH,
        )
    ]
