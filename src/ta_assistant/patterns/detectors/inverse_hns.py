"""Inverse Head-and-Shoulders (H&S bottom): L H L H L with the middle low (head)
below both shoulder lows; neckline through the two reaction highs."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import (
    PatternCandidate,
    classify,
    closeness_conf,
)
from ta_assistant.patterns.trendlines import fit_trendline

PATTERN_TYPE = "head_and_shoulders_bottom"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    piv = ctx.pivots
    for i in range(len(piv) - 1, 3, -1):
        rs, h2, head, h1, ls = piv[i], piv[i - 1], piv[i - 2], piv[i - 3], piv[i - 4]
        if [ls.kind, h1.kind, head.kind, h2.kind, rs.kind] != ["L", "H", "L", "H", "L"]:
            continue
        if not (head.price < ls.price and head.price < rs.price):
            continue
        shoulder_tol = max(0.05 * ls.price, 2.0 * ctx.atr_at(rs.idx))
        if abs(ls.price - rs.price) > shoulder_tol:
            continue

        neckline = fit_trendline([h1.idx, h2.idx], [h1.price, h2.price])
        # Breakout = neckline at the right shoulder (do NOT extrapolate to "now",
        # which would give nonsense on an old pattern).
        breakout = neckline.value_at(rs.idx)
        height = neckline.value_at(head.idx) - head.price
        if height <= 0 or breakout <= 0:
            continue
        stop = rs.price - 0.5 * ctx.atr_at(rs.idx)
        status, breakout_idx = classify(ctx, rs.idx, breakout, stop, rs.provisional)
        return [
            PatternCandidate(
                pattern_type=PATTERN_TYPE,
                timeframe=ctx.timeframe,
                status=status,
                geometry_confidence=closeness_conf(ls.price, rs.price, shoulder_tol),
                pivots=[ls, h1, head, h2, rs],
                levels={
                    "breakout": breakout,
                    "neckline": breakout,
                    "neckline_slope": neckline.slope,
                    "neckline_intercept": neckline.intercept,
                    "target": breakout + height,
                    "stop": stop,
                    "pattern_height": height,
                    "head_low": head.price,
                },
                region_start_idx=ls.idx,
                region_end_idx=rs.idx,
                breakout_idx=breakout_idx,
            )
        ]
    return []
