"""Hand-built OHLCV frames engineered to trigger each regime metric deterministically."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def make_daily(
    closes: Sequence[float],
    *,
    vols: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
    highs: Sequence[float] | None = None,
    start: str = "2021-01-04",
) -> pd.DataFrame:
    """OHLCV frame on a business-day index named `ts`. Sensible defaults for H/L/vol."""
    n = len(closes)
    idx = pd.bdate_range(start=start, periods=n, name="ts")
    c = [float(x) for x in closes]
    lo = [float(x) for x in lows] if lows is not None else [x * 0.995 for x in c]
    hi = [float(x) for x in highs] if highs is not None else [x * 1.005 for x in c]
    op = [c[0]] + c[:-1]  # open = prior close
    vo = [float(x) for x in vols] if vols is not None else [1_000_000.0] * n
    return pd.DataFrame(
        {"open": op, "high": hi, "low": lo, "close": c, "volume": vo}, index=idx
    )


def linear(start_val: float, step: float, n: int) -> list[float]:
    return [start_val + step * i for i in range(n)]


# --- primary-trend scenarios -------------------------------------------------


def bull_trend(n: int = 320) -> pd.DataFrame:
    """Steady uptrend: price > 50 > 150 > 200, 200-day rising."""
    return make_daily(linear(100.0, 0.5, n))


def bear_trend(n: int = 320) -> pd.DataFrame:
    """Steady downtrend: price < 200-day, MAs stacked bearishly."""
    return make_daily(linear(300.0, -0.5, n))


def power_trend_on(n: int = 140) -> pd.DataFrame:
    """Strong, smooth uptrend so the daily low stays above the 21-EMA and 21-EMA > 50-SMA."""
    return make_daily(linear(100.0, 1.2, n))


# --- weekly Weinstein-stage scenarios (function uses close + 30-wk MA) -------


def weekly_stage2(n: int = 60) -> pd.DataFrame:
    return make_daily(linear(100.0, 1.0, n), start="2024-01-05")


def weekly_stage4(n: int = 60) -> pd.DataFrame:
    return make_daily(linear(200.0, -1.0, n), start="2024-01-05")


def weekly_stage1(n: int = 60) -> pd.DataFrame:
    # decline for 30 wks, then flat -> 30-wk MA flat after a down phase
    closes = linear(200.0, -1.0, 30) + [170.0] * 30
    return make_daily(closes, start="2024-01-05")


def weekly_stage3(n: int = 60) -> pd.DataFrame:
    # rise for 30 wks, then flat -> 30-wk MA flat after an up phase
    closes = linear(100.0, 1.0, 30) + [130.0] * 30
    return make_daily(closes, start="2024-01-05")


# --- Dow confirmation --------------------------------------------------------


def confirming_up() -> tuple[pd.DataFrame, pd.DataFrame]:
    return bull_trend(200), bull_trend(200)


def divergence() -> tuple[pd.DataFrame, pd.DataFrame]:
    industrials = bull_trend(200)
    transports = make_daily([150.0] * 200)  # flat -> "side"
    return industrials, transports


# --- distribution days -------------------------------------------------------


def distribution_heavy(n: int = 120, count: int = 6) -> pd.DataFrame:
    closes = [100.0] * n
    vols = [1_000_000.0] * n
    positions = [n - 2 - 3 * k for k in range(count)]  # all within the last 25 sessions
    for p in positions:
        closes[p] = closes[p - 1] * 0.99  # down ~1%
        vols[p] = vols[p - 1] * 1.3  # higher volume than the prior day
    return make_daily(closes, vols=vols)


def distribution_calm(n: int = 120) -> pd.DataFrame:
    return make_daily(linear(100.0, 0.2, n))  # quiet uptrend, no distribution


def distribution_heavy_on_uptrend(n: int = 320, count: int = 6) -> pd.DataFrame:
    """A confirmed uptrend (above a rising 200-day) that nonetheless takes `count`
    distribution days in the last ~5 weeks -> 'uptrend under pressure'."""
    closes = linear(100.0, 0.5, n)
    vols = [1_000_000.0] * n
    for p in [n - 2 - 3 * k for k in range(count)]:
        closes[p] = closes[p - 1] * 0.99
        vols[p] = vols[p - 1] * 1.3
    return make_daily(closes, vols=vols)


# --- follow-through day ------------------------------------------------------


def ftd_frame() -> pd.DataFrame:
    closes = linear(100.0, 1.0, 40)  # 0..39 rally to 139
    closes += [139 - 2 * (i + 1) for i in range(10)]  # 40..49 correction down to 119 (the low)
    rally = [120.0, 120.5]  # 50,51
    rally += [120.5 * 1.02]  # 52 = day 4 of attempt: FTD, +2%
    rally += [123.5, 124.5, 125.5, 126.5, 127.5]  # 53..57 continue up
    closes += rally
    vols = [1_000_000.0] * len(closes)
    vols[52] = 2_500_000.0  # higher volume than day 51 on the FTD
    return make_daily(closes, vols=vols)


# --- relative strength / breadth / liquidity ---------------------------------


def basket_mostly_above(above: int = 8, below: int = 2, n: int = 260) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for i in range(above):
        out[f"UP{i}"] = make_daily(linear(50.0, 0.4, n))["close"]
    for i in range(below):
        out[f"DN{i}"] = make_daily(linear(200.0, -0.4, n))["close"]
    return out


def basket_bars_mostly_highs(
    highs: int = 7, lows: int = 2, n: int = 260
) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for i in range(highs):
        out[f"UP{i}"] = make_daily(linear(50.0, 0.4, n))
    for i in range(lows):
        out[f"DN{i}"] = make_daily(linear(200.0, -0.4, n))
    return out


def liquidity_expanding_frames(n: int = 130) -> dict[str, pd.DataFrame]:
    """HY outperforming IG, dollar falling, software & high-beta leading -> expanding."""
    return {
        "HYG": make_daily(linear(75.0, 0.10, n)),
        "LQD": make_daily([110.0] * n),
        "DXY": make_daily(linear(105.0, -0.05, n)),
        "IGV": make_daily(linear(80.0, 0.30, n)),
        "SPY": make_daily(linear(400.0, 0.20, n)),
        "SPHB": make_daily(linear(70.0, 0.25, n)),
        "SPLV": make_daily([65.0] * n),
    }


def liquidity_flat_frames(n: int = 130) -> dict[str, pd.DataFrame]:
    """Everything flat -> within the deadband -> Not Known."""
    return {
        "HYG": make_daily([75.0] * n),
        "LQD": make_daily([110.0] * n),
        "DXY": make_daily([105.0] * n),
        "IGV": make_daily([80.0] * n),
        "SPY": make_daily([400.0] * n),
        "SPHB": make_daily([70.0] * n),
        "SPLV": make_daily([65.0] * n),
    }
