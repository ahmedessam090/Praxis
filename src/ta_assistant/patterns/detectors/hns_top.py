"""Head-and-shoulders TOP (bearish warning): H L H L H, head above both shoulders;
neckline through the two reaction lows. NOT a short entry — context that upside is capped."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import (
    BEARISH,
    PatternCandidate,
    classify_bearish,
    closeness_conf,
)
from ta_assistant.patterns.trendlines import fit_trendline

PATTERN_TYPE = "head_and_shoulders_top"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    piv = ctx.pivots
    for i in range(len(piv) - 1, 3, -1):
        rs, l2, head, l1, ls = piv[i], piv[i - 1], piv[i - 2], piv[i - 3], piv[i - 4]
        if [ls.kind, l1.kind, head.kind, l2.kind, rs.kind] != ["H", "L", "H", "L", "H"]:
            continue
        if not (head.price > ls.price and head.price > rs.price):
            continue
        shoulder_tol = max(0.05 * ls.price, 2.0 * ctx.atr_at(rs.idx))
        if abs(ls.price - rs.price) > shoulder_tol:
            continue

        neckline = fit_trendline([l1.idx, l2.idx], [l1.price, l2.price])
        breakdown = neckline.value_at(rs.idx)
        height = head.price - neckline.value_at(head.idx)
        if height <= 0 or breakdown <= 0:
            continue
        stop = head.price + 0.5 * ctx.atr_at(rs.idx)
        status, breakdown_idx = classify_bearish(ctx, rs.idx, breakdown, stop, rs.provisional)
        return [
            PatternCandidate(
                pattern_type=PATTERN_TYPE,
                timeframe=ctx.timeframe,
                status=status,
                geometry_confidence=closeness_conf(ls.price, rs.price, shoulder_tol),
                pivots=[ls, l1, head, l2, rs],
                levels={
                    "breakout": breakdown,
                    "neckline": breakdown,
                    "neckline_slope": neckline.slope,
                    "neckline_intercept": neckline.intercept,
                    "target": breakdown - height,
                    "stop": stop,
                    "pattern_height": height,
                    "head_high": head.price,
                },
                region_start_idx=ls.idx,
                region_end_idx=rs.idx,
                breakout_idx=breakdown_idx,
                direction=BEARISH,
            )
        ]
    return []
