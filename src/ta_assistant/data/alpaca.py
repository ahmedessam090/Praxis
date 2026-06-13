"""Alpaca price/OHLCV provider (Phase 1)."""

from __future__ import annotations


def get_bars(symbol: str, timeframe: str = "1Day", limit: int = 300) -> list[dict[str, float]]:
    """Fetch OHLCV bars for `symbol`.

    Phase 1: import alpaca-py INSIDE this function and map to a list of bar dicts.
    """
    raise NotImplementedError("Phase 1: wire alpaca-py here (import inside this function).")
