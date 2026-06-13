"""ATR-scaled ZigZag swing-pivot detection.

Produces an alternating sequence of significant swing highs/lows. The reversal
threshold is ATR-relative (with a percentage floor) so it adapts across price
scales and volatility regimes. The final pivot is the running extreme of the
active leg and is marked `provisional` (the leg can still extend) — which is what
lets the engine flag "just forming" patterns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ta_assistant.patterns.indicators import atr
from ta_assistant.patterns.types import Pivot


def atr_zigzag(
    df: pd.DataFrame,
    atr_mult: float = 3.0,
    atr_len: int = 14,
    min_pct: float = 0.03,
) -> list[Pivot]:
    n = len(df)
    if n < 3:
        return []

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    index = list(df.index)
    atr_arr = atr(df, atr_len).to_numpy(dtype=float)

    def reversal(ref_price: float, i: int) -> float:
        a = atr_arr[i] if not np.isnan(atr_arr[i]) else 0.0
        return max(atr_mult * a, min_pct * ref_price)

    def make(idx: int, price: float, kind: str, provisional: bool = False) -> Pivot:
        ts = pd.Timestamp(index[idx]).to_pydatetime()
        return Pivot(idx=idx, ts=ts, price=price, kind=kind, provisional=provisional)

    pivots: list[Pivot] = []
    trend = 0  # +1 up, -1 down, 0 unknown
    up_i, up_px = 0, highs[0]  # running high of the current up-leg
    dn_i, dn_px = 0, lows[0]  # running low of the current down-leg

    for i in range(1, n):
        if highs[i] > up_px:
            up_px, up_i = highs[i], i
        if lows[i] < dn_px:
            dn_px, dn_i = lows[i], i

        if trend > 0:
            if up_px - lows[i] >= reversal(up_px, i):
                pivots.append(make(up_i, up_px, "H"))
                trend = -1
                up_px, up_i, dn_px, dn_i = highs[i], i, lows[i], i
        elif trend < 0:
            if highs[i] - dn_px >= reversal(dn_px, i):
                pivots.append(make(dn_i, dn_px, "L"))
                trend = 1
                up_px, up_i, dn_px, dn_i = highs[i], i, lows[i], i
        else:  # unknown: take the first qualifying move in either direction
            if up_px - lows[i] >= reversal(up_px, i):
                pivots.append(make(up_i, up_px, "H"))
                trend = -1
                up_px, up_i, dn_px, dn_i = highs[i], i, lows[i], i
            elif highs[i] - dn_px >= reversal(dn_px, i):
                pivots.append(make(dn_i, dn_px, "L"))
                trend = 1
                up_px, up_i, dn_px, dn_i = highs[i], i, lows[i], i

    if trend > 0:
        pivots.append(make(up_i, up_px, "H", provisional=True))
    elif trend < 0:
        pivots.append(make(dn_i, dn_px, "L", provisional=True))

    return pivots
