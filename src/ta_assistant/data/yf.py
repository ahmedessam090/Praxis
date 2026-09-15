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


# yfinance's sector names / sectorKey -> our GICS keys (regime.universe.SECTOR_ETF keys).
_GICS_BY_YF = {
    "technology": "technology",
    "communication services": "communication",
    "consumer cyclical": "discretionary",
    "consumer defensive": "staples",
    "healthcare": "health",
    "financial services": "financials",
    "industrials": "industrials",
    "energy": "energy",
    "basic materials": "materials",
    "utilities": "utilities",
    "real estate": "real_estate",
}


def _map_yf_sector(raw: str) -> str | None:
    """Map a yfinance sector string (display name or sectorKey, e.g. 'Consumer Cyclical' or
    'financial-services') to our GICS key. Returns None if it isn't recognized."""
    norm = str(raw or "").strip().lower().replace("-", " ").replace("_", " ")
    if not norm:
        return None
    if norm in _GICS_BY_YF:
        return _GICS_BY_YF[norm]
    if norm in set(_GICS_BY_YF.values()):  # a sectorKey that already equals one of our keys
        return norm
    return None


def fetch_sector(symbol: str, tries: int = 3) -> str | None:
    """Best-effort GICS sector for a ticker from yfinance, mapped to our keys. Retries because
    yfinance's metadata endpoint is flaky; returns None if it can't be resolved."""
    import yfinance as yf

    for _ in range(max(1, tries)):
        try:
            ticker = yf.Ticker(symbol)
            try:
                info = ticker.get_info() or {}
            except Exception:  # noqa: BLE001 - get_info can throw; fall back to the .info prop
                info = getattr(ticker, "info", {}) or {}
            for field in ("sectorKey", "sector", "sectorDisp"):
                key = _map_yf_sector(info.get(field, ""))
                if key:
                    return key
        except Exception:  # noqa: BLE001 - transient network/parse error -> retry
            continue
    return None
