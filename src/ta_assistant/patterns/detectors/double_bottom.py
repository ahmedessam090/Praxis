"""Double bottom: two ~equal swing lows with a reaction high (neckline) between."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import (
    SUPPORT,
    PatternCandidate,
    classify,
    closeness_conf,
)

PATTERN_TYPE = "double_bottom"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    piv = ctx.pivots
    for i in range(len(piv) - 1, 1, -1):  # most-recent first
        low2, mid, low1 = piv[i], piv[i - 1], piv[i - 2]
        if not (low1.kind == "L" and mid.kind == "H" and low2.kind == "L"):
            continue
        eq_tol = max(0.03 * low1.price, 1.5 * ctx.atr_at(low2.idx))
        if abs(low1.price - low2.price) > eq_tol:
            continue
        if mid.price <= max(low1.price, low2.price):
            continue

        neckline = mid.price
        base = (low1.price + low2.price) / 2.0
        height = neckline - base
        if height <= 0:
            continue
        stop = min(low1.price, low2.price) - 0.5 * ctx.atr_at(low2.idx)
        status, breakout_idx = classify(ctx, low2.idx, neckline, stop, low2.provisional)
        return [
            PatternCandidate(
                pattern_type=PATTERN_TYPE,
                timeframe=ctx.timeframe,
                status=status,
                geometry_confidence=closeness_conf(low1.price, low2.price, eq_tol),
                pivots=[low1, mid, low2],
                levels={
                    "breakout": neckline,
                    "neckline": neckline,
                    "target": neckline + height,
                    "stop": stop,
                    "pattern_height": height,
                },
                region_start_idx=low1.idx,
                region_end_idx=low2.idx,
                breakout_idx=breakout_idx,
                tier=SUPPORT,  # confirmation/context, not a standalone trade
            )
        ]
    return []
