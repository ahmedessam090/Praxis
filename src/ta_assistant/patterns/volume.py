"""Volume confirmation features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ta_assistant.patterns.indicators import obv


def breakout_volume_ratio(df: pd.DataFrame, idx: int, length: int = 20) -> float:
    """Volume at bar `idx` divided by the average of the prior `length` bars."""
    vol = df["volume"].to_numpy(dtype=float)
    if idx <= 0:
        return 0.0
    lo = max(0, idx - length)
    window = vol[lo:idx]
    avg = float(window.mean()) if window.size else 0.0
    return float(vol[idx] / avg) if avg > 0 else 0.0


def obv_slope(df: pd.DataFrame, start: int, end: int) -> float:
    """Normalized slope of OBV over [start, end] (positive = accumulation)."""
    series = obv(df).to_numpy(dtype=float)[start : end + 1]
    if len(series) < 2:
        return 0.0
    x = np.arange(len(series), dtype=float)
    slope = float(np.polyfit(x, series, 1)[0])
    scale = float(np.abs(series).mean()) or 1.0
    return slope / scale


def is_drying_up(df: pd.DataFrame, start: int, end: int) -> bool:
    """True if volume is contracting across [start, end] (bullish in a base/handle)."""
    vol = df["volume"].to_numpy(dtype=float)[start : end + 1]
    if len(vol) < 3:
        return False
    x = np.arange(len(vol), dtype=float)
    return bool(np.polyfit(x, vol, 1)[0] < 0)
