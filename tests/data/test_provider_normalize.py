"""Provider normalization (adjustment math + tz handling) — pure, no network."""

from __future__ import annotations

import pandas as pd

from ta_assistant.data import stooq, yf


def test_yf_normalize_applies_split_adjustment() -> None:
    idx = pd.DatetimeIndex(pd.to_datetime(["2020-01-02", "2020-01-03"])).tz_localize(
        "America/New_York"
    )
    raw = pd.DataFrame(
        {
            "Open": [100.0, 50.0],
            "High": [110.0, 55.0],
            "Low": [90.0, 45.0],
            "Close": [100.0, 50.0],
            "Adj Close": [50.0, 50.0],  # day1 close 100 but adj 50 -> a later 2:1 split
            "Volume": [1000, 2000],
            "Dividends": [0.0, 0.0],
            "Stock Splits": [0.0, 2.0],
        },
        index=idx,
    )
    out = yf._normalize(raw)

    assert list(out.columns) == yf.COLUMNS
    assert out["close"].iloc[0] == 50.0  # adjusted close
    assert out["open"].iloc[0] == 50.0  # 100 * (50/100)
    assert out["high"].iloc[0] == 55.0  # 110 * 0.5
    assert out["adj_factor"].iloc[0] == 0.5
    assert out["raw_close"].iloc[0] == 100.0  # raw kept
    assert out.index.tz is None  # tz dropped
    assert str(out.index[0].date()) == "2020-01-02"


def test_yf_normalize_empty() -> None:
    assert yf._normalize(pd.DataFrame()).empty


def test_stooq_normalize() -> None:
    raw = pd.DataFrame(
        {
            "Date": ["2019-05-01", "2019-05-02"],
            "Open": [10.0, 11.0],
            "High": [10.5, 11.5],
            "Low": [9.5, 10.5],
            "Close": [10.2, 11.2],
            "Volume": [500, 600],
        }
    )
    out = stooq._normalize(raw)
    assert list(out.columns) == yf.COLUMNS
    assert out["close"].iloc[1] == 11.2
    assert out["adj_factor"].iloc[0] == 1.0
    assert str(out.index[0].date()) == "2019-05-01"
