"""Bear flag (bearish warning): steep down-pole + shallow upward drift; warns of more downside."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import BEARISH, PatternCandidate, classify_bearish
from ta_assistant.patterns.detectors.bull_flag import _MAX_POLE_BARS, _MIN_FLAG_BARS, _MIN_POLE_GAIN

PATTERN_TYPE = "bear_flag"


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    piv = ctx.pivots
    n = len(ctx.df)
    highs = ctx.df["high"].to_numpy(dtype=float)
    for i in range(len(piv) - 1, 0, -1):
        bottom, top = piv[i], piv[i - 1]
        if not (top.kind == "H" and bottom.kind == "L"):
            continue
        pole_bars = bottom.idx - top.idx
        if pole_bars <= 0 or pole_bars > _MAX_POLE_BARS:
            continue
        pole_height = top.price - bottom.price
        if pole_height / top.price < _MIN_POLE_GAIN:
            continue
        if n - 1 - bottom.idx < _MIN_FLAG_BARS:
            continue

        flag_high = float(highs[bottom.idx + 1 :].max())
        if flag_high > bottom.price + 0.5 * pole_height:  # drifted up too far -> not a flag
            continue
        breakdown = bottom.price
        if breakdown <= 0:
            continue
        stop = flag_high + 0.5 * ctx.atr_at(n - 1)
        status, breakdown_idx = classify_bearish(
            ctx, bottom.idx, breakdown, stop, piv[-1].provisional
        )
        return [
            PatternCandidate(
                pattern_type=PATTERN_TYPE,
                timeframe=ctx.timeframe,
                status=status,
                geometry_confidence=0.6,
                pivots=[top, bottom],
                levels={
                    "breakout": breakdown,
                    "target": breakdown - pole_height,
                    "stop": stop,
                    "pattern_height": pole_height,
                    "pole_top": top.price,
                    "flag_high": flag_high,
                },
                region_start_idx=top.idx,
                region_end_idx=n - 1,
                breakout_idx=breakdown_idx,
                direction=BEARISH,
            )
        ]
    return []
