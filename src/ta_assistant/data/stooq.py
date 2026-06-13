"""Stooq fallback provider — free daily CSV with decades of history.

Used when yfinance rate-limits or returns empty. Stooq daily data is split
adjusted; we treat its close as adjusted (adj_factor = 1.0) for fallback purposes.
"""

from __future__ import annotations

import io

import pandas as pd

from ta_assistant.data.yf import COLUMNS

_URL = "https://stooq.com/q/d/l/?s={sym}.us&i=d"


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty or "Close" not in raw.columns:
        return pd.DataFrame(columns=COLUMNS)

    idx = pd.DatetimeIndex(pd.to_datetime(raw["Date"])).normalize()
    out = pd.DataFrame(index=idx)
    out["open"] = raw["Open"].to_numpy(dtype=float)
    out["high"] = raw["High"].to_numpy(dtype=float)
    out["low"] = raw["Low"].to_numpy(dtype=float)
    out["close"] = raw["Close"].to_numpy(dtype=float)
    out["volume"] = raw["Volume"].to_numpy(dtype=float) if "Volume" in raw.columns else 0.0
    out["raw_close"] = out["close"].to_numpy()
    out["adj_factor"] = 1.0
    out.index.name = "ts"
    return out.dropna(how="any")


def fetch_daily(symbol: str) -> pd.DataFrame:
    import requests

    resp = requests.get(
        _URL.format(sym=symbol.lower()),
        timeout=30,
        headers={"User-Agent": "ta-assistant/0.1"},
    )
    resp.raise_for_status()
    return _normalize(pd.read_csv(io.StringIO(resp.text)))
