"""Bull flag: a steep flagpole (L->H run) then a shallow consolidation; the
pole height projects the target off the breakout."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import PatternCandidate, classify

PATTERN_TYPE = "bull_flag"

_MIN_POLE_GAIN = 0.15
_MAX_POLE_BARS = 25
_MIN_FLAG_BARS = 2


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    piv = ctx.pivots
    n = len(ctx.df)
    lows = ctx.df["low"].to_numpy(dtype=float)
    for i in range(len(piv) - 1, 0, -1):
        top, base = piv[i], piv[i - 1]
        if not (base.kind == "L" and top.kind == "H"):
            continue
        pole_bars = top.idx - base.idx
        if pole_bars <= 0 or pole_bars > _MAX_POLE_BARS:
            continue
        pole_height = top.price - base.price
        if pole_height / base.price < _MIN_POLE_GAIN:
            continue
        if n - 1 - top.idx < _MIN_FLAG_BARS:  # need a consolidation after the pole
            continue

        flag_low = float(lows[top.idx + 1 :].min())
        if flag_low < top.price - 0.5 * pole_height:  # too deep -> not a flag
            continue

        breakout = top.price
        stop = flag_low - 0.5 * ctx.atr_at(n - 1)
        status, breakout_idx = classify(ctx, top.idx, breakout, stop, piv[-1].provisional)
        return [
            PatternCandidate(
                pattern_type=PATTERN_TYPE,
                timeframe=ctx.timeframe,
                status=status,
                geometry_confidence=0.65,
                pivots=[base, top],
                levels={
                    "breakout": breakout,
                    "target": breakout + pole_height,
                    "stop": stop,
                    "pattern_height": pole_height,
                    "pole_base": base.price,
                    "flag_low": flag_low,
                },
                region_start_idx=base.idx,
                region_end_idx=n - 1,
                breakout_idx=breakout_idx,
            )
        ]
    return []
