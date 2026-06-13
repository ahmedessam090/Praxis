"""yfinance provider — all-time adjusted daily history (Phase 1 primary).

`history(auto_adjust=False)` returns raw OHLC + `Adj Close`; we store adjusted
O/H/L/C (= raw * Adj Close / Close, the geometry source of truth) plus the raw
close and the adjustment factor. yfinance is imported inside the function so it
never reaches the Temporal workflow sandbox.
"""

from __future__ import annotations

import pandas as pd

COLUMNS = ["open", "high", "low", "close", "volume", "raw_close", "adj_factor"]


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Map a yfinance history() frame (auto_adjust=False) to our adjusted schema."""
    if raw is None or raw.empty or "Adj Close" not in raw.columns:
        return pd.DataFrame(columns=COLUMNS)

    idx = pd.DatetimeIndex(raw.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    idx = idx.normalize()

    factor = (raw["Adj Close"] / raw["Close"]).to_numpy(dtype=float)
    out = pd.DataFrame(index=idx)
    out["open"] = raw["Open"].to_numpy(dtype=float) * factor
    out["high"] = raw["High"].to_numpy(dtype=float) * factor
    out["low"] = raw["Low"].to_numpy(dtype=float) * factor
    out["close"] = raw["Adj Close"].to_numpy(dtype=float)
    out["volume"] = raw["Volume"].to_numpy(dtype=float)
    out["raw_close"] = raw["Close"].to_numpy(dtype=float)
    out["adj_factor"] = factor
    out.index.name = "ts"
    return out.dropna(how="any")


def fetch_daily(symbol: str) -> pd.DataFrame:
    """All-time adjusted daily OHLCV for `symbol`."""
    import yfinance as yf

    raw = yf.Ticker(symbol).history(
        period="max", interval="1d", auto_adjust=False, actions=True, repair=True
    )
    return _normalize(raw)
