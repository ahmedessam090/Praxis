"""Rectangle (range): horizontal resistance + horizontal support; long the upside break."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import PatternCandidate, classify
from ta_assistant.patterns.levels import cluster_prices

PATTERN_TYPE = "rectangle"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    highs = [p for p in ctx.pivots if p.kind == "H"]
    lows = [p for p in ctx.pivots if p.kind == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return []

    atr_ref = ctx.atr_at(len(ctx.df) - 1)
    tol = max(0.02 * ctx.last_close, 1.5 * atr_ref)
    res_clusters = cluster_prices([p.price for p in highs], tol)
    sup_clusters = cluster_prices([p.price for p in lows], tol)
    resistance, rtouch = res_clusters[0]
    support, stouch = sup_clusters[0]
    if rtouch < 2 or stouch < 2 or resistance <= support:
        return []

    height = resistance - support
    stop = support - 0.5 * atr_ref
    touch_h = [p for p in highs if abs(p.price - resistance) <= tol]
    touch_l = [p for p in lows if abs(p.price - support) <= tol]
    region_start = min(touch_h[0].idx, touch_l[0].idx)
    region_end = max(touch_h[-1].idx, touch_l[-1].idx)
    status, breakout_idx = classify(ctx, region_end, resistance, stop, ctx.pivots[-1].provisional)
    return [
        PatternCandidate(
            pattern_type=PATTERN_TYPE,
            timeframe=ctx.timeframe,
            status=status,
            geometry_confidence=min(0.6 + 0.05 * (rtouch + stouch), 0.9),
            pivots=[*touch_l, *touch_h],
            levels={
                "breakout": resistance,
                "resistance": resistance,
                "support": support,
                "target": resistance + height,
                "stop": stop,
                "pattern_height": height,
            },
            region_start_idx=region_start,
            region_end_idx=region_end,
            breakout_idx=breakout_idx,
        )
    ]
