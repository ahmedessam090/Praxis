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


def rectangle_df(steps: int = 10) -> pd.DataFrame:
    # resistance 100 (x2), support 80 (x3), breakout 115 -> target 120
    return ohlcv_from_close(zigzag_closes([90, 80, 100, 80, 100, 80, 115], steps))


def symmetrical_triangle_df(steps: int = 10) -> pd.DataFrame:
    # falling highs 100,96,92 + rising lows 70,78,84 converge, break up to 105
    return ohlcv_from_close(zigzag_closes([70, 100, 78, 96, 84, 92, 105], steps))


def falling_wedge_df(steps: int = 10) -> pd.DataFrame:
    # both rails down (highs 100,90,82 / lows 80,76,74), resistance steeper, break up 95
    return ohlcv_from_close(zigzag_closes([100, 80, 90, 76, 82, 74, 95], steps))


def ascending_channel_df(steps: int = 10) -> pd.DataFrame:
    # parallel rising rails (highs 90,100,110 / lows 70,80,90,100), continuation to 115
    return ohlcv_from_close(zigzag_closes([70, 90, 80, 100, 90, 110, 100, 115], steps))


def triple_bottom_df(steps: int = 10) -> pd.DataFrame:
    # three equal lows at 70, neckline 85, break up to 95 -> target 100
    return ohlcv_from_close(zigzag_closes([100, 70, 85, 70, 85, 70, 95], steps))


# ---- bearish (warning) generators (mirror the bullish ones, topping/declining) ----


def hns_top_df(steps: int = 10) -> pd.DataFrame:
    # LS/RS 105, head 115, neckline 97, breakdown to 88 -> target 79
    return ohlcv_from_close(zigzag_closes([90, 105, 97, 115, 97, 105, 88], steps))


def double_top_df(steps: int = 10) -> pd.DataFrame:
    # two tops at 120, neckline 105, breakdown to 98 -> target 90
    return ohlcv_from_close(zigzag_closes([90, 120, 105, 120, 98], steps))


def triple_top_df(steps: int = 10) -> pd.DataFrame:
    # three tops at 100, neckline 90, breakdown to 88 -> target 80
    return ohlcv_from_close(zigzag_closes([80, 100, 90, 100, 90, 100, 88], steps))


def descending_triangle_df(steps: int = 10) -> pd.DataFrame:
    # falling highs 100,92,84 + flat support 70, breakdown to 55
    return ohlcv_from_close(zigzag_closes([100, 70, 92, 70, 84, 70, 55], steps))


def rising_wedge_df(steps: int = 10) -> pd.DataFrame:
    # both rails up, support steeper, converging, breakdown to 80
    return ohlcv_from_close(zigzag_closes([80, 70, 86, 80, 90, 86, 80], steps))


def descending_channel_df(steps: int = 10) -> pd.DataFrame:
    # parallel falling rails (highs 100,92,84 / lows 85,77,69), breakdown to 60
    return ohlcv_from_close(zigzag_closes([100, 85, 92, 77, 84, 69, 60], steps))


def bear_flag_df(steps: int = 10) -> pd.DataFrame:
    # down-pole 80->50 (height 30), shallow up drift to 62, breakdown to 48
    return ohlcv_from_close(zigzag_closes([80, 50, 62, 48], steps))
