"""Ascending triangle: flat resistance (a cluster of ~equal highs) + rising
support (higher lows beneath it)."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import PatternCandidate, classify
from ta_assistant.patterns.levels import cluster_prices

PATTERN_TYPE = "ascending_triangle"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    highs = [p for p in ctx.pivots if p.kind == "H"]
    lows = [p for p in ctx.pivots if p.kind == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return []

    atr_ref = ctx.atr_at(len(ctx.df) - 1)
    flat_tol = max(0.02 * highs[-1].price, 1.5 * atr_ref)

    clusters = cluster_prices([p.price for p in highs], flat_tol)
    resistance, touches = clusters[0]  # strongest (most-touched) level
    if touches < 2:
        return []

    touch_highs = [p for p in highs if abs(p.price - resistance) <= flat_tol]
    base_lows = [p for p in lows if p.price < resistance - 0.1 * flat_tol]
    recent_l = base_lows[-3:]
    if len(recent_l) < 2:
        return []
    if not all(recent_l[k].price < recent_l[k + 1].price for k in range(len(recent_l) - 1)):
        return []

    lowest = min(p.price for p in recent_l)
    height = resistance - lowest
    if height <= 0:
        return []
    stop = recent_l[-1].price - 0.5 * ctx.atr_at(recent_l[-1].idx)
    region_start = min(touch_highs[0].idx, recent_l[0].idx)
    region_end = max(touch_highs[-1].idx, recent_l[-1].idx)
    status, breakout_idx = classify(ctx, region_end, resistance, stop, ctx.pivots[-1].provisional)
    return [
        PatternCandidate(
            pattern_type=PATTERN_TYPE,
            timeframe=ctx.timeframe,
            status=status,
            geometry_confidence=min(0.6 + 0.1 * touches, 0.9),
            pivots=[*recent_l, *touch_highs],
            levels={
                "breakout": resistance,
                "resistance": resistance,
                "target": resistance + height,
                "stop": stop,
                "pattern_height": height,
            },
            region_start_idx=region_start,
            region_end_idx=region_end,
            breakout_idx=breakout_idx,
        )
    ]
