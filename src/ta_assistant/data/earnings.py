"""Best-effort next-earnings-date lookup via yfinance (free, no key).

yfinance scrapes Yahoo and is documented-flaky, so every path is wrapped and
returns None on any failure — the earnings note simply doesn't fire. yfinance is
imported inside the function (Temporal sandbox discipline)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class EarningsInfo:
    next_date: date
    days_until: int


def fetch_earnings_info(symbol: str, today: date) -> EarningsInfo | None:
    try:
        import pandas as pd
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        next_date: date | None = None

        try:
            cal = ticker.get_calendar()
            raw = None
            if isinstance(cal, dict):
                raw = cal.get("Earnings Date")
                if isinstance(raw, (list, tuple)) and raw:
                    raw = raw[0]
            elif cal is not None and "Earnings Date" in getattr(cal, "index", []):
                raw = cal.loc["Earnings Date"][0]
            if raw is not None:
                next_date = pd.Timestamp(raw).date()
        except Exception:  # noqa: BLE001
            next_date = None

        if next_date is None:
            try:
                table = ticker.get_earnings_dates(limit=8)
                if table is not None and len(table):
                    future = [pd.Timestamp(d).date() for d in table.index]
                    future = [d for d in future if d >= today]
                    if future:
                        next_date = min(future)
            except Exception:  # noqa: BLE001
                next_date = None

        if next_date is None:
            return None
        return EarningsInfo(next_date=next_date, days_until=(next_date - today).days)
    except Exception:  # noqa: BLE001
        return None
