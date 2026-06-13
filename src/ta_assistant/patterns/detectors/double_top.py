"""Double top (bearish warning): two ~equal highs with a reaction low (neckline) between."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import (
    BEARISH,
    PatternCandidate,
    classify_bearish,
    closeness_conf,
)

PATTERN_TYPE = "double_top"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    piv = ctx.pivots
    for i in range(len(piv) - 1, 1, -1):
        high2, mid, high1 = piv[i], piv[i - 1], piv[i - 2]
        if not (high1.kind == "H" and mid.kind == "L" and high2.kind == "H"):
            continue
        eq_tol = max(0.03 * high1.price, 1.5 * ctx.atr_at(high2.idx))
        if abs(high1.price - high2.price) > eq_tol or mid.price >= min(high1.price, high2.price):
            continue

        neckline = mid.price
        top = (high1.price + high2.price) / 2.0
        height = top - neckline
        if height <= 0:
            continue
        stop = max(high1.price, high2.price) + 0.5 * ctx.atr_at(high2.idx)
        status, breakdown_idx = classify_bearish(ctx, high2.idx, neckline, stop, high2.provisional)
        return [
            PatternCandidate(
                pattern_type=PATTERN_TYPE,
                timeframe=ctx.timeframe,
                status=status,
                geometry_confidence=closeness_conf(high1.price, high2.price, eq_tol),
                pivots=[high1, mid, high2],
                levels={
                    "breakout": neckline,
                    "neckline": neckline,
                    "target": neckline - height,
                    "stop": stop,
                    "pattern_height": height,
                },
                region_start_idx=high1.idx,
                region_end_idx=high2.idx,
                breakout_idx=breakdown_idx,
                direction=BEARISH,
            )
        ]
    return []
