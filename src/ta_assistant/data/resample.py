"""Resample adjusted daily OHLCV to weekly (W-FRI) and monthly (ME).

The most-recent weekly/monthly bar is flagged ``is_partial`` when its period has
not closed as of ``now`` (passed in — never read the clock here), so the engine
can treat a still-forming bar correctly.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
_OHLCV = ["open", "high", "low", "close", "volume"]


def _resample(daily: pd.DataFrame, rule: str, period_freq: str, now: datetime) -> pd.DataFrame:
    out = daily[_OHLCV].resample(rule, label="right", closed="right").agg(_AGG).dropna(how="any")
    out["is_partial"] = False
    if len(out):
        last_period_end = out.index.to_period(period_freq)[-1].end_time
        if pd.Timestamp(now) < last_period_end:
            out.iloc[-1, out.columns.get_loc("is_partial")] = True
    return out


def to_weekly(daily: pd.DataFrame, now: datetime) -> pd.DataFrame:
    return _resample(daily, "W-FRI", "W-FRI", now)


def to_monthly(daily: pd.DataFrame, now: datetime) -> pd.DataFrame:
    return _resample(daily, "ME", "M", now)
