"""Synthetic OHLCV builders for deterministic pattern tests."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def ohlcv_from_close(
    closes: Sequence[float],
    start: str = "2020-01-01",
    volume: Sequence[float] | float = 1_000_000.0,
    band: float = 0.0,
) -> pd.DataFrame:
    """Build a daily OHLCV frame from a close path (high/low = close +/- band)."""
    close = np.asarray(closes, dtype=float)
    idx = pd.bdate_range(start, periods=len(close))
    vol = (
        np.full(len(close), volume, dtype=float)
        if np.isscalar(volume)
        else np.asarray(volume, float)
    )
    return pd.DataFrame(
        {
            "open": close,
            "high": close + band,
            "low": close - band,
            "close": close,
            "volume": vol,
        },
        index=idx,
    )


def zigzag_closes(targets: Sequence[float], steps_per_leg: int) -> list[float]:
    """Piecewise-linear close path hitting each target price in turn."""
    out = [float(targets[0])]
    for target in targets[1:]:
        leg = np.linspace(out[-1], float(target), steps_per_leg + 1)[1:]
        out.extend(leg.tolist())
    return out


# ---- pattern generators (close paths chosen so ATR-ZigZag yields clean pivots) ----


def double_bottom_df(steps: int = 10) -> pd.DataFrame:
    # L1=90, neckline=105, L2=90, breakout up to 130 -> target 120
    return ohlcv_from_close(zigzag_closes([120, 90, 105, 90, 130], steps))


def inverse_hns_df(steps: int = 10) -> pd.DataFrame:
    # LS=95, neckline=103 (flat), head=85, RS=95, breakout 125 -> target 121
    return ohlcv_from_close(zigzag_closes([110, 95, 103, 85, 103, 95, 125], steps))


def ascending_triangle_df(steps: int = 10) -> pd.DataFrame:
    # flat resistance 100, rising lows 80<88<94, breakout 115
    return ohlcv_from_close(zigzag_closes([100, 80, 100, 88, 100, 94, 115], steps))


def cup_handle_df(steps: int = 10) -> pd.DataFrame:
    # rim 100, cup bottom 70, handle low 90, breakout 120 -> depth 30, target 130
    return ohlcv_from_close(zigzag_closes([100, 70, 100, 90, 120], steps))


def bull_flag_df(steps: int = 10) -> pd.DataFrame:
    # pole 50->80 (height 30), shallow flag to 70, breakout 95 -> target 110
    return ohlcv_from_close(zigzag_closes([50, 80, 70, 95], steps))
