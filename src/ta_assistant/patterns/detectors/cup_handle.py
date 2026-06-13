"""Cup-and-handle: rounded base (left rim -> bottom -> right rim ~ left rim) with
a shallow handle pullback; cup depth projects the target off the rim breakout."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import (
    PatternCandidate,
    classify,
    closeness_conf,
)

PATTERN_TYPE = "cup_and_handle"

_MIN_CUP_DEPTH_FRAC = 0.10  # cup must be at least 10% of rim price deep


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    piv = ctx.pivots
    n = len(ctx.df)
    lows = ctx.df["low"].to_numpy(dtype=float)
    for i in range(len(piv) - 1, 1, -1):
        right, bottom, left = piv[i], piv[i - 1], piv[i - 2]
        if not (left.kind == "H" and bottom.kind == "L" and right.kind == "H"):
            continue
        rim_tol = max(0.05 * left.price, 2.0 * ctx.atr_at(right.idx))
        if abs(left.price - right.price) > rim_tol:
            continue
        rim = (left.price + right.price) / 2.0
        depth = rim - bottom.price
        if depth <= 0 or depth < _MIN_CUP_DEPTH_FRAC * rim:
            continue

        # Handle = shallow pullback after the right rim (optional).
        end_idx = right.idx
        handle_low = right.price
        after = lows[right.idx + 1 :]
        if after.size:
            handle_low = float(after.min())
            end_idx = n - 1

        breakout = max(left.price, right.price)
        stop = min(handle_low, right.price) - 0.5 * ctx.atr_at(end_idx)
        status, breakout_idx = classify(ctx, right.idx, breakout, stop, piv[-1].provisional)
        return [
            PatternCandidate(
                pattern_type=PATTERN_TYPE,
                timeframe=ctx.timeframe,
                status=status,
                geometry_confidence=closeness_conf(left.price, right.price, rim_tol),
                pivots=[left, bottom, right],
                levels={
                    "breakout": breakout,
                    "target": breakout + depth,
                    "stop": stop,
                    "pattern_height": depth,
                    "rim": rim,
                    "cup_bottom": bottom.price,
                    "handle_low": handle_low,
                },
                region_start_idx=left.idx,
                region_end_idx=end_idx,
                breakout_idx=breakout_idx,
            )
        ]
    return []
