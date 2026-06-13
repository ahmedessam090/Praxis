"""Indicator snapshots + deterministic analytical notes / warnings.

Pure (no I/O): operates on already-loaded adjusted frames + detected patterns, so
it's trivially testable and replay-safe. The daily frame drives volatility /
liquidity / extension / 52-week / gap notes.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ta_assistant.patterns.indicators import (
    atr_pct,
    avg_dollar_volume,
    ema,
    realized_vol,
    relative_volume,
    rolling_high,
    rolling_low,
    rsi,
    sma,
)
from ta_assistant.synthesis.schema import (
    AnalyticalNote,
    DetectedPattern,
    IndicatorSnapshot,
    NoteSeverity,
    Timeframe,
)

_SEV_RANK = {"warning": 0, "caution": 1, "info": 2}


def _last(series: pd.Series) -> float | None:
    if len(series) == 0:
        return None
    value = series.iloc[-1]
    return float(value) if pd.notna(value) else None


def snapshot(df: pd.DataFrame, tf: Timeframe) -> IndicatorSnapshot:
    close = df["close"]
    last = float(close.iloc[-1])
    n = len(df)
    s50 = _last(sma(close, 50)) if n >= 50 else None
    s150 = _last(sma(close, 150)) if n >= 150 else None
    s200 = _last(sma(close, 200)) if n >= 200 else None

    hi52 = lo52 = pct_hi = None
    if tf == Timeframe.DAILY and n >= 2:
        hi52 = float(rolling_high(df["high"], min(252, n)).iloc[-1])
        lo52 = float(rolling_low(df["low"], min(252, n)).iloc[-1])
        pct_hi = 100.0 * (last / hi52 - 1.0) if hi52 else None

    pct_50 = 100.0 * (last / s50 - 1.0) if s50 else None
    trend_pass = None
    if (
        tf == Timeframe.DAILY
        and s50 is not None
        and s150 is not None
        and s200 is not None
        and hi52 is not None
    ):
        s200_series = sma(close, 200)
        rising = len(s200_series) >= 21 and s200_series.iloc[-1] > s200_series.iloc[-21]
        trend_pass = bool(last > s50 > s150 > s200 and rising and last >= 0.75 * hi52)

    return IndicatorSnapshot(
        timeframe=tf,
        close=last,
        sma50=s50,
        sma150=s150,
        sma200=s200,
        ema21=_last(ema(close, 21)) if n >= 21 else None,
        rsi14=_last(rsi(close, 14)) if n >= 15 else None,
        atr_pct=_last(atr_pct(df, 14)),
        realized_vol=_last(realized_vol(close, 20)) if tf == Timeframe.DAILY and n >= 21 else None,
        rel_volume=_last(relative_volume(df, 20)),
        avg_dollar_volume_20=_last(avg_dollar_volume(df, 20)),
        high_52w=hi52,
        low_52w=lo52,
        pct_from_52w_high=pct_hi,
        pct_above_sma50=pct_50,
        trend_template_pass=trend_pass,
    )


def analyze_notes(
    daily: pd.DataFrame,
    snapshots: dict[Timeframe, IndicatorSnapshot],
    patterns: Sequence[DetectedPattern],
    earnings_days: int | None = None,
) -> list[AnalyticalNote]:
    notes: list[AnalyticalNote] = []

    def add(key: str, sev: str, msg: str) -> None:
        notes.append(AnalyticalNote(key=key, severity=NoteSeverity(sev), message=msg))

    snap = snapshots.get(Timeframe.DAILY)
    if snap is not None:
        if snap.atr_pct is not None and snap.atr_pct > 5.0:
            add(
                "volatility_high",
                "warning",
                f"High volatility: ATR {snap.atr_pct:.1f}% of price; size down, widen stops.",
            )
        elif snap.atr_pct is not None and snap.atr_pct > 3.5:
            add(
                "volatility_high",
                "caution",
                f"Elevated volatility: ATR {snap.atr_pct:.1f}% of price.",
            )

        adv = snap.avg_dollar_volume_20
        if adv is not None and adv < 5e6:
            add(
                "liquidity_thin",
                "warning",
                f"Thin liquidity: ~${adv / 1e6:.1f}M/day dollar volume; slippage/gap risk.",
            )
        elif adv is not None and adv < 20e6:
            add("liquidity_thin", "caution", f"Moderate liquidity: ~${adv / 1e6:.1f}M/day.")

        if snap.pct_above_sma50 is not None and snap.pct_above_sma50 > 20:
            add(
                "extended_above_50dma",
                "warning",
                f"Very extended: {snap.pct_above_sma50:.0f}% above the 50-day MA.",
            )
        elif snap.pct_above_sma50 is not None and snap.pct_above_sma50 > 10:
            add(
                "extended_above_50dma",
                "caution",
                f"Extended: {snap.pct_above_sma50:.0f}% above the 50-day MA; prefer a pullback.",
            )

        if snap.rsi14 is not None and snap.rsi14 > 80:
            add("overbought_rsi", "warning", f"Overbought: RSI(14) = {snap.rsi14:.0f}.")
        elif snap.rsi14 is not None and snap.rsi14 > 70:
            add("overbought_rsi", "caution", f"Overbought: RSI(14) = {snap.rsi14:.0f}.")

        if snap.trend_template_pass is True:
            add("trend_template", "info", "Trend template intact: price > 50 > 150 > 200-day MAs.")
        elif snap.sma200 is not None and snap.close < snap.sma200:
            add(
                "trend_not_confirmed",
                "warning",
                "Below the 200-day MA — long setups here fight the prevailing trend.",
            )

        if snap.pct_from_52w_high is not None and snap.pct_from_52w_high >= -2.0:
            add(
                "near_52w_high",
                "info",
                f"Near 52w high ({snap.pct_from_52w_high:+.1f}%); base breakouts favored.",
            )
        if snap.low_52w is not None and snap.close <= 1.05 * snap.low_52w:
            add(
                "near_52w_low",
                "warning",
                "Near 52-week low — a falling-knife context; require a confirmed reversal base.",
            )

    for p in patterns:
        if p.status.value in ("triggered", "confirmed"):
            ratio = p.volume.get("breakout_volume_ratio")
            if ratio is not None and ratio < 1.0:
                add(
                    "weak_breakout_volume",
                    "warning",
                    f"Weak breakout volume on {p.pattern_type}: {ratio:.1f}x avg (want >1.5x).",
                )
                break
            if ratio is not None and ratio < 1.5:
                add(
                    "weak_breakout_volume",
                    "caution",
                    f"Light breakout volume on {p.pattern_type}: {ratio:.1f}x the 20-day average.",
                )
                break

    if len(daily) >= 6:
        closes = daily["close"].to_numpy(dtype=float)
        opens = daily["open"].to_numpy(dtype=float)
        for k in range(len(daily) - 5, len(daily)):
            gap = opens[k] / closes[k - 1] - 1.0
            if abs(gap) > 0.05:
                add(
                    "recent_gap",
                    "caution" if gap < 0 else "info",
                    f"Recent {'down' if gap < 0 else 'up'} gap of {gap * 100:+.0f}%.",
                )
                break

    if len(daily) < 200:
        add(
            "low_history",
            "info",
            f"Limited history ({len(daily)} daily bars); 200-day MA / 52-week levels are partial.",
        )

    if earnings_days is not None and earnings_days >= 0:
        if earnings_days <= 14:
            add(
                "earnings_soon",
                "warning",
                f"Earnings in {earnings_days} days — binary gap risk; size down or wait.",
            )
        elif earnings_days <= 30:
            add("earnings_soon", "caution", f"Earnings in ~{earnings_days} days.")

    notes.sort(key=lambda nt: (_SEV_RANK[nt.severity.value], nt.key))
    return notes
