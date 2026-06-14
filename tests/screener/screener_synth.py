"""Synthetic OHLCV frames for screener tests (uptrend/downtrend/flat)."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def make_daily(closes: Sequence[float], *, vol: float = 1_000_000.0,
               start: str = "2023-01-02") -> pd.DataFrame:
    n = len(closes)
    idx = pd.bdate_range(start=start, periods=n, name="ts")
    c = [float(x) for x in closes]
    return pd.DataFrame(
        {
            "open": [c[0]] + c[:-1],
            "high": [x * 1.005 for x in c],
            "low": [x * 0.995 for x in c],
            "close": c,
            "volume": [vol] * n,
        },
        index=idx,
    )


def linear(start_val: float, step: float, n: int) -> list[float]:
    return [start_val + step * i for i in range(n)]


def uptrend(n: int = 300, start_val: float = 50.0, step: float = 0.4) -> pd.DataFrame:
    return make_daily(linear(start_val, step, n))


def downtrend(n: int = 300, start_val: float = 300.0, step: float = -0.4) -> pd.DataFrame:
    return make_daily(linear(start_val, step, n))


def flat(n: int = 300, val: float = 100.0) -> pd.DataFrame:
    return make_daily([val] * n)
