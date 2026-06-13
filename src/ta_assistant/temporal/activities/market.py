"""Market-data activities.

Pre-phase: deterministic stubs returning canned data so the durability skeleton
runs with zero API keys. Phase 1 replaces these with real Alpaca/yfinance fetches
and pandas/numpy indicator math — all imported HERE (inside activities), never in
workflow code.
"""

from __future__ import annotations

from temporalio import activity


@activity.defn
async def fetch_bars(symbol: str) -> list[float]:
    """STUB: canned closing prices for `symbol`."""
    activity.logger.info("fetch_bars stub for %s", symbol)
    return [100.0, 101.5, 103.0, 102.0, 104.5, 106.0]


@activity.defn
async def compute_indicators(prices: list[float]) -> dict[str, float]:
    """STUB: trivial SMA + last close."""
    return {"sma": sum(prices) / len(prices), "last": prices[-1]}
