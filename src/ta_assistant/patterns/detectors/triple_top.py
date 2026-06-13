"""Triple top (bearish warning): three ~equal highs with two reaction lows."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import (
    BEARISH,
    PatternCandidate,
    classify_bearish,
    closeness_conf,
)

PATTERN_TYPE = "triple_top"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    piv = ctx.pivots
    for i in range(len(piv) - 1, 3, -1):
        high3, low2, high2, low1, high1 = piv[i], piv[i - 1], piv[i - 2], piv[i - 3], piv[i - 4]
        if [high1.kind, low1.kind, high2.kind, low2.kind, high3.kind] != ["H", "L", "H", "L", "H"]:
            continue
        eq_tol = max(0.03 * ctx.last_close, 1.5 * ctx.atr_at(high3.idx))
        tops = [high1.price, high2.price, high3.price]
        if max(tops) - min(tops) > eq_tol:
            continue
        neckline = min(low1.price, low2.price)
        top = sum(tops) / 3.0
        height = top - neckline
        if height <= 0:
            continue
        stop = max(tops) + 0.5 * ctx.atr_at(high3.idx)
        status, breakdown_idx = classify_bearish(ctx, high3.idx, neckline, stop, high3.provisional)
        return [
            PatternCandidate(
                pattern_type=PATTERN_TYPE,
                timeframe=ctx.timeframe,
                status=status,
                geometry_confidence=closeness_conf(max(tops), min(tops), eq_tol),
                pivots=[high1, low1, high2, low2, high3],
                levels={
                    "breakout": neckline,
                    "neckline": neckline,
                    "target": neckline - height,
                    "stop": stop,
                    "pattern_height": height,
                },
                region_start_idx=high1.idx,
                region_end_idx=high3.idx,
                breakout_idx=breakdown_idx,
                direction=BEARISH,
            )
        ]
    return []
