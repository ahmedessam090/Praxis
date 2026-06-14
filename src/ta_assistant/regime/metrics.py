"""Pure, book-grounded market-condition metrics — one function per classical rule.

Every function takes the standard adjusted-OHLCV frame (columns open/high/low/close/
volume, ascending DatetimeIndex named `ts`) and returns a small frozen result with a
`status` in {"bullish","neutral","bearish"}. No I/O, no clock reads — trivially
testable and replay-safe. `pillars.py` turns these into the dashboard's RegimeMetric/
RegimePillar objects and the cross-asset interpretation.

Sources: Dow Theory + Edwards & Magee (trend, averages-confirm), Weinstein (stage),
O'Neil/IBD (distribution days, follow-through day), Minervini (Power Trend), Murphy
(intermarket / liquidity).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from ta_assistant.patterns.indicators import ema, sma

BULLISH, NEUTRAL, BEARISH = "bullish", "neutral", "bearish"


# --------------------------------------------------------------------------- helpers


def _sma_last(close: pd.Series, length: int) -> float | None:
    if len(close) < length:
        return None
    return float(sma(close, length).iloc[-1])


def _series_chg(df: pd.DataFrame, lookback: int = 63) -> float:
    close = df["close"]
    n = len(close)
    lb = min(lookback, n - 1)
    if lb <= 0:
        return 0.0
    return float(close.iloc[-1] / close.iloc[-1 - lb] - 1.0)


def _ratio_series(a: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
    left, right = a["close"].align(b["close"], join="inner")
    return (left / right).dropna()


def _ratio_chg(a: pd.DataFrame, b: pd.DataFrame, lookback: int = 63) -> float | None:
    r = _ratio_series(a, b)
    n = len(r)
    lb = min(lookback, n - 1)
    if lb <= 0:
        return None
    return float(r.iloc[-1] / r.iloc[-1 - lb] - 1.0)


def _signal(chg: float | None, deadband: float) -> int:
    """+1 / 0 / -1 with a deadband (None -> 0)."""
    if chg is None:
        return 0
    if chg > deadband:
        return 1
    if chg < -deadband:
        return -1
    return 0


# --------------------------------------------------------------- 1. Primary trend


@dataclass(frozen=True)
class MaTrend:
    close: float
    sma50: float | None
    sma150: float | None
    sma200: float | None
    stacked: bool  # close > 50 > 150 > 200
    above_200: bool
    ma200_rising: bool
    status: str


def trend_vs_mas(df: pd.DataFrame) -> MaTrend:
    """Dow/Minervini: price vs 50/150/200 MAs, stacking, rising 200-day."""
    close = df["close"]
    n = len(close)
    last = float(close.iloc[-1])
    s50 = _sma_last(close, 50)
    s150 = _sma_last(close, 150)
    s200 = _sma_last(close, 200)
    stacked = bool(
        s50 is not None and s150 is not None and s200 is not None and last > s50 > s150 > s200
    )
    above_200 = bool(s200 is not None and last > s200)
    rising = False
    if n >= 221:
        s200s = sma(close, 200)
        rising = bool(s200s.iloc[-1] > s200s.iloc[-21])
    if stacked and rising:
        status = BULLISH
    elif s200 is not None and last < s200:
        status = BEARISH
    else:
        status = NEUTRAL
    return MaTrend(last, s50, s150, s200, stacked, above_200, rising, status)


# --------------------------------------------------------------- 2. Weinstein stage


@dataclass(frozen=True)
class StageRead:
    stage: int  # 1..4 (0 = indeterminate)
    label: str
    ma30: float | None
    price_above_ma30: bool
    ma30_rising: bool
    status: str


def weinstein_stage(weekly: pd.DataFrame, look: int = 5) -> StageRead:
    """Weinstein 4-stage cycle off the 30-week MA + its slope (on a WEEKLY frame)."""
    close = weekly["close"]
    n = len(close)
    if n < look + 1:
        return StageRead(0, "Indeterminate", None, False, False, NEUTRAL)
    ma = sma(close, 30)
    ma_last = float(ma.iloc[-1])
    price = float(close.iloc[-1])
    above = price > ma_last
    slope_now = float(ma.iloc[-1] - ma.iloc[-1 - look])
    eps = 0.01 * ma_last  # ~1% over `look` weeks = "flat"
    rising = slope_now > eps
    falling = slope_now < -eps
    if rising:
        stage, label = (2, "Stage 2 — Advancing") if above else (1, "Stage 1 — Basing")
    elif falling:
        stage, label = (4, "Stage 4 — Declining") if not above else (3, "Stage 3 — Topping")
    else:  # flat — disambiguate by the prior slope
        prev = float(ma.iloc[-1 - look] - ma.iloc[-1 - 2 * look]) if n > 2 * look else 0.0
        stage, label = (3, "Stage 3 — Topping") if prev > 0 else (1, "Stage 1 — Basing")
    status = {2: BULLISH, 1: NEUTRAL, 3: NEUTRAL, 4: BEARISH}[stage]
    return StageRead(stage, label, ma_last, above, bool(rising), status)


# --------------------------------------------------------------- 3. Dow confirmation


@dataclass(frozen=True)
class TrendDir:
    direction: str  # "up" | "down" | "side"
    change_pct: float
    near_high: bool
    near_low: bool


def _trend_dir(df: pd.DataFrame, lookback: int = 126, thresh: float = 0.03) -> TrendDir:
    close = df["close"]
    n = len(close)
    lb = min(lookback, n - 1)
    if lb <= 0:
        return TrendDir("side", 0.0, False, False)
    chg = float(close.iloc[-1] / close.iloc[-1 - lb] - 1.0)
    hi = float(df["high"].iloc[-lb:].max())
    lo = float(df["low"].iloc[-lb:].min())
    last = float(close.iloc[-1])
    near_high = last >= 0.97 * hi
    near_low = last <= 1.03 * lo
    if chg > thresh and near_high:
        d = "up"
    elif chg < -thresh and near_low:
        d = "down"
    else:
        d = "side"
    return TrendDir(d, chg, near_high, near_low)


@dataclass(frozen=True)
class DowRead:
    industrials: TrendDir
    transports: TrendDir
    confirms: bool
    status: str
    note: str


def dow_confirmation(industrials: pd.DataFrame, transports: pd.DataFrame) -> DowRead:
    """Dow Theory: Industrials & Transports must confirm one another."""
    a = _trend_dir(industrials)
    b = _trend_dir(transports)
    if a.direction == "up" and b.direction == "up":
        return DowRead(a, b, True, BULLISH, "Industrials & Transports both confirming new highs.")
    if a.direction == "down" and b.direction == "down":
        return DowRead(a, b, True, BEARISH, "Both averages in downtrends — confirmed weakness.")
    return DowRead(
        a,
        b,
        False,
        NEUTRAL,
        f"Non-confirmation: Industrials {a.direction}, Transports {b.direction} (divergence).",
    )


# --------------------------------------------------------------- 4. Distribution days


@dataclass(frozen=True)
class DistRead:
    count: int
    window: int
    dates: list[datetime] = field(default_factory=list)
    status: str = NEUTRAL


def distribution_days(df: pd.DataFrame, window: int = 25, drop: float = 0.002) -> DistRead:
    """O'Neil: index down >= `drop` on higher volume than the prior session, within the
    last `window` sessions. 5-6 => uptrend under pressure."""
    close = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)
    idx = df.index
    n = len(close)
    dates: list[datetime] = []
    for i in range(max(1, n - window), n):
        pct = close[i] / close[i - 1] - 1.0
        if pct <= -drop and vol[i] > vol[i - 1]:
            dates.append(pd.Timestamp(idx[i]).to_pydatetime())
    c = len(dates)
    status = BEARISH if c >= 5 else (NEUTRAL if c >= 3 else BULLISH)
    return DistRead(c, window, dates, status)


# --------------------------------------------------------------- 5. Follow-through day


@dataclass(frozen=True)
class FtdRead:
    found: bool
    ts: datetime | None
    days_since: int | None
    gain_pct: float | None
    status: str


def follow_through_day(
    df: pd.DataFrame, gain: float = 0.0125, min_day: int = 4, lookback: int = 40
) -> FtdRead:
    """O'Neil: after a correction low + rally attempt, an index up >= `gain` on higher
    volume than the prior day, on day `min_day`+ of the attempt, confirms a new uptrend."""
    close = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    idx = df.index
    n = len(close)
    if n < min_day + 2:
        return FtdRead(False, None, None, None, NEUTRAL)
    w = min(lookback, n)
    seg_start = n - w
    low_pos = seg_start + int(low[seg_start:n].argmin())  # the rally-attempt low (day 1)
    ftd = None
    for i in range(low_pos + min_day - 1, n):
        pct = close[i] / close[i - 1] - 1.0
        if pct >= gain and vol[i] > vol[i - 1]:
            ftd = i
            break
    if ftd is None:
        return FtdRead(False, None, None, None, NEUTRAL)
    days_since = n - 1 - ftd
    return FtdRead(
        True,
        pd.Timestamp(idx[ftd]).to_pydatetime(),
        days_since,
        float(close[ftd] / close[ftd - 1] - 1.0),
        BULLISH,
    )


# --------------------------------------------------------------- 6. Minervini Power Trend


@dataclass(frozen=True)
class PowerTrendRead:
    on: bool
    low_above_ema21_days: int
    ema21_above_sma50_days: int
    status: str


def power_trend(
    df: pd.DataFrame, low_days: int = 10, ema_days: int = 5, ema_len: int = 21, sma_len: int = 50
) -> PowerTrendRead:
    """Minervini/Webster Power Trend: the daily LOW stays above the 21-EMA for >= 10
    sessions AND the 21-EMA stays above the 50-SMA for >= 5 sessions."""
    close = df["close"]
    n = len(close)
    e = ema(close, ema_len)
    s = sma(close, sma_len)
    low = df["low"]
    low_above = 0
    for k in range(1, min(low_days, n) + 1):
        if float(low.iloc[-k]) > float(e.iloc[-k]):
            low_above += 1
        else:
            break
    ema_above = 0
    for k in range(1, min(ema_days, n) + 1):
        if float(e.iloc[-k]) > float(s.iloc[-k]):
            ema_above += 1
        else:
            break
    on = low_above >= low_days and ema_above >= ema_days
    if on:
        status = BULLISH
    elif n > 0 and float(close.iloc[-1]) < float(s.iloc[-1]):
        status = BEARISH
    else:
        status = NEUTRAL
    return PowerTrendRead(on, low_above, ema_above, status)


# --------------------------------------------------------------- 7. Breadth proxies


@dataclass(frozen=True)
class RatioRead:
    last: float | None
    sma: float | None
    rising: bool
    pct_above_sma: float | None
    status: str


def relative_strength(a: pd.DataFrame, b: pd.DataFrame, length: int = 50) -> RatioRead:
    """Trend of the a/b ratio (Murphy relative strength). `rising` => a outperforming b.
    Caller decides whether rising means risk-on or risk-off for that pair."""
    r = _ratio_series(a, b)
    n = len(r)
    if n == 0:
        return RatioRead(None, None, False, None, NEUTRAL)
    last = float(r.iloc[-1])
    sm = float(sma(r, min(length, n)).iloc[-1])
    lb = min(20, n - 1)
    rising = bool(lb > 0 and r.iloc[-1] > r.iloc[-1 - lb] and last >= sm)
    falling = bool(lb > 0 and r.iloc[-1] < r.iloc[-1 - lb] and last < sm)
    pct = 100.0 * (last / sm - 1.0) if sm else None
    status = BULLISH if rising else (BEARISH if falling else NEUTRAL)
    return RatioRead(last, sm, rising, pct, status)


@dataclass(frozen=True)
class BreadthRead:
    pct: float | None
    above: int
    total: int
    status: str


def pct_above_ma(closes: dict[str, pd.Series], length: int = 200) -> BreadthRead:
    """% of a basket trading above their `length`-day MA (>60 bullish / <40 bearish)."""
    above = 0
    total = 0
    for close in closes.values():
        if len(close) < length:
            continue
        m = float(sma(close, length).iloc[-1])
        total += 1
        if float(close.iloc[-1]) > m:
            above += 1
    if total == 0:
        return BreadthRead(None, 0, 0, NEUTRAL)
    pct = 100.0 * above / total
    status = BULLISH if pct >= 60 else (BEARISH if pct <= 40 else NEUTRAL)
    return BreadthRead(pct, above, total, status)


@dataclass(frozen=True)
class HiLoRead:
    net: int
    highs: int
    lows: int
    status: str


def net_new_highs_lows(bars: dict[str, pd.DataFrame], window: int = 252) -> HiLoRead:
    """Net basket members making a new `window`-bar high vs low on the latest bar."""
    nh = nl = 0
    for df in bars.values():
        n = len(df)
        if n < 20:
            continue
        w = min(window, n)
        hi = float(df["high"].iloc[-w:].max())
        lo = float(df["low"].iloc[-w:].min())
        if float(df["high"].iloc[-1]) >= hi * 0.999:
            nh += 1
        elif float(df["low"].iloc[-1]) <= lo * 1.001:
            nl += 1
    net = nh - nl
    status = BULLISH if net > 0 else (BEARISH if net < 0 else NEUTRAL)
    return HiLoRead(net, nh, nl, status)


# --------------------------------------------------------------- 8. Single-asset trend


@dataclass(frozen=True)
class SeriesTrend:
    last: float | None
    sma50: float | None
    sma200: float | None
    above_200: bool
    rising: bool
    change_pct: float
    status: str


def series_trend(df: pd.DataFrame, lookback: int = 63) -> SeriesTrend:
    """Generic single-series trend (commodities, dollar, VIX, bonds). `status` is the
    raw price trend (rising => bullish FOR THAT SERIES); the pillar maps it to risk-on/off."""
    close = df["close"]
    n = len(close)
    if n == 0:
        return SeriesTrend(None, None, None, False, False, 0.0, NEUTRAL)
    last = float(close.iloc[-1])
    s50 = _sma_last(close, 50)
    s200 = _sma_last(close, 200)
    above = bool(s200 is not None and last > s200)
    chg = _series_chg(df, lookback)
    rising = chg > 0.0
    if above and rising:
        status = BULLISH
    elif s200 is not None and not above and not rising:
        status = BEARISH
    else:
        status = NEUTRAL
    return SeriesTrend(last, s50, s200, above, rising, chg, status)


# --------------------------------------------------------------- 9. Liquidity cycle (strict)


@dataclass(frozen=True)
class LiquidityRead:
    state: str  # expanding | turning_up | contracting | turning_down | not_known
    label: str
    signals: dict[str, str] = field(default_factory=dict)
    clear_count: int = 0
    status: str = NEUTRAL


_LIQ_LABEL = {
    "expanding": "Expanding",
    "turning_up": "Turning up (early)",
    "contracting": "Contracting",
    "turning_down": "Turning down (early)",
    "not_known": "Not Known",
}


def liquidity_cycle(
    frames: dict[str, pd.DataFrame],
    *,
    hyg: str,
    lqd: str,
    dxy: str,
    software: str,
    spy: str,
    high_beta: str,
    low_vol: str,
    deadband: float = 0.015,
    lookback: int = 63,
) -> LiquidityRead:
    """Strict liquidity-cycle read from classical proxies — credit spreads (HY vs IG),
    the US dollar, long-duration *software* leadership (IGV vs SPY) and high-beta vs
    low-vol. Only calls a direction when a strong majority agree; otherwise "Not Known".

    Signals (each +1 expanding / -1 contracting / 0 unclear within the deadband):
      credit   : HY/IG ratio rising  => spreads tightening => liquidity expanding
      dollar   : DXY falling          => global liquidity easing
      software : IGV/SPY rising        => long-duration risk bid => ample liquidity
      risk     : high-beta/low-vol rising => risk-seeking
    """
    sig: dict[str, int] = {}

    def have(*names: str) -> bool:
        return all(n in frames and len(frames[n]) > 5 for n in names)

    if have(hyg, lqd):
        sig["credit (HY/IG)"] = _signal(_ratio_chg(frames[hyg], frames[lqd], lookback), deadband)
    if have(dxy):
        sig["dollar (DXY)"] = -_signal(_series_chg(frames[dxy], lookback), deadband)
    if have(software, spy):
        sig["software (IGV/SPY)"] = _signal(
            _ratio_chg(frames[software], frames[spy], lookback), deadband
        )
    if have(high_beta, low_vol):
        sig["risk (high-beta/low-vol)"] = _signal(
            _ratio_chg(frames[high_beta], frames[low_vol], lookback), deadband
        )

    pos = sum(1 for v in sig.values() if v > 0)
    neg = sum(1 for v in sig.values() if v < 0)
    clear = pos + neg

    def words(v: int) -> str:
        return "expanding" if v > 0 else ("contracting" if v < 0 else "unclear")

    readable = {k: words(v) for k, v in sig.items()}

    # Strict: need >= 3 clear signals AND strong agreement; else "Not Known".
    if len(sig) < 3 or clear < 3:
        state = "not_known"
    elif neg == 0 and pos >= 3:
        state = "expanding" if pos >= 4 else "turning_up"
    elif pos == 0 and neg >= 3:
        state = "contracting" if neg >= 4 else "turning_down"
    elif pos >= 3 and neg <= 1:
        state = "turning_up"
    elif neg >= 3 and pos <= 1:
        state = "turning_down"
    else:
        state = "not_known"

    status = {
        "expanding": BULLISH,
        "turning_up": BULLISH,
        "contracting": BEARISH,
        "turning_down": BEARISH,
        "not_known": NEUTRAL,
    }[state]
    return LiquidityRead(state, _LIQ_LABEL[state], readable, clear, status)
