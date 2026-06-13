"""Daily -> weekly/monthly resampling + partial-bar flagging (pure)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ta_assistant.data.resample import to_monthly, to_weekly


def _daily(n: int, start: str) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=n)
    close = pd.Series(range(1, n + 1), index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": 100.0},
        index=idx,
    )


def test_weekly_ohlcv_aggregation() -> None:
    # 2024-01-01 is a Monday; first full Mon-Fri week is values 1..5.
    wk = to_weekly(_daily(10, "2024-01-01"), now=datetime(2024, 2, 1))
    first = wk.iloc[0]
    assert first["open"] == 1.0
    assert first["close"] == 5.0
    assert first["high"] == 5.5
    assert first["low"] == 0.5
    assert first["volume"] == 500.0
    assert not bool(wk["is_partial"].iloc[-1])  # 'now' is well past the last week


def test_partial_last_week_flagged() -> None:
    # Mon-Wed only, 'now' is mid-week -> the current week is still forming.
    wk = to_weekly(_daily(3, "2024-01-01"), now=datetime(2024, 1, 3))
    assert bool(wk["is_partial"].iloc[-1])


def test_monthly_aggregation() -> None:
    mo = to_monthly(_daily(40, "2024-01-01"), now=datetime(2024, 6, 1))
    assert len(mo) >= 2
    assert mo.iloc[0]["open"] == 1.0  # first January business day
    assert not bool(mo["is_partial"].iloc[-1])
