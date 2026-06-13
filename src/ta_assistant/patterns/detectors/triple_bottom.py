"""Triple bottom: three ~equal swing lows with two reaction highs; long the neckline break."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import PatternCandidate, classify, closeness_conf

PATTERN_TYPE = "triple_bottom"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    piv = ctx.pivots
    for i in range(len(piv) - 1, 3, -1):
        low3, h2, low2, h1, low1 = piv[i], piv[i - 1], piv[i - 2], piv[i - 3], piv[i - 4]
        if [low1.kind, h1.kind, low2.kind, h2.kind, low3.kind] != ["L", "H", "L", "H", "L"]:
            continue
        eq_tol = max(0.03 * ctx.last_close, 1.5 * ctx.atr_at(low3.idx))
        lows = [low1.price, low2.price, low3.price]
        if max(lows) - min(lows) > eq_tol:
            continue
        neckline = max(h1.price, h2.price)
        base = sum(lows) / 3.0
        height = neckline - base
        if height <= 0:
            continue
        stop = min(lows) - 0.5 * ctx.atr_at(low3.idx)
        status, breakout_idx = classify(ctx, low3.idx, neckline, stop, low3.provisional)
        return [
            PatternCandidate(
                pattern_type=PATTERN_TYPE,
                timeframe=ctx.timeframe,
                status=status,
                geometry_confidence=closeness_conf(max(lows), min(lows), eq_tol),
                pivots=[low1, h1, low2, h2, low3],
                levels={
                    "breakout": neckline,
                    "neckline": neckline,
                    "target": neckline + height,
                    "stop": stop,
                    "pattern_height": height,
                },
                region_start_idx=low1.idx,
                region_end_idx=low3.idx,
                breakout_idx=breakout_idx,
            )
        ]
    return []
