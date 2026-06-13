"""Ascending channel: parallel rising rails; long a break of the upper rail."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import PatternCandidate, classify, fit_rails

PATTERN_TYPE = "ascending_channel"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    rails = fit_rails(ctx)
    if rails is None:
        return []
    upper, lower, highs, lows, rstart, rend = rails
    if not (upper.slope > 0 and lower.slope > 0):
        return []
    # roughly parallel
    if abs(upper.slope - lower.slope) > 0.3 * abs(lower.slope):
        return []

    breakout = upper.value_at(rend)
    width = upper.value_at(rend) - lower.value_at(rend)
    if width <= 0:
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
                "target": breakout + width,
                "stop": stop,
                "pattern_height": width,
                "neckline_slope": upper.slope,
                "neckline_intercept": upper.intercept,
            },
            region_start_idx=rstart,
            region_end_idx=rend,
            breakout_idx=breakout_idx,
        )
    ]
