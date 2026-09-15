"""Provider orchestrator: yfinance primary, Stooq fallback."""

from __future__ import annotations

import logging

import pandas as pd

from ta_assistant.data import stooq, yf

logger = logging.getLogger(__name__)


def get_daily_history(symbol: str) -> tuple[pd.DataFrame, str]:
    """Return (adjusted-daily OHLCV, source). Falls back to Stooq on yfinance failure."""
    try:
        df = yf.fetch_daily(symbol)
        if len(df) > 0:
            return df, "yfinance"
        logger.warning("yfinance returned empty for %s; falling back to Stooq", symbol)
    except Exception as exc:  # noqa: BLE001 - any provider error should fall back
        logger.warning("yfinance failed for %s (%s); falling back to Stooq", symbol, exc)
    return stooq.fetch_daily(symbol), "stooq"


def get_sector(symbol: str) -> str | None:
    """Best-effort GICS sector for a ticker (yfinance metadata, multi-try). None if unresolved."""
    try:
        return yf.fetch_sector(symbol)
    except Exception as exc:  # noqa: BLE001 - never let a sector lookup break the caller
        logger.warning("sector lookup failed for %s (%s)", symbol, exc)
        return None
