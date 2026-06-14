"""Build the `RegimeChart` time-series behind each pillar, so the dashboard draws a real
charted view of everything considered. Windowed (~2 trading years) + rounded so the
persisted snapshot stays compact. Pure (no I/O)."""

from __future__ import annotations

import pandas as pd

from ta_assistant.patterns.indicators import sma
from ta_assistant.regime import metrics as M
from ta_assistant.regime import universe as U
from ta_assistant.synthesis.schema import (
    ChartMarker,
    RegimeCandle,
    RegimeChart,
    RegimePoint,
    RegimeSeries,
)

WINDOW = 504  # ~2 trading years
_MA = [(50, "#2962ff"), (150, "#ff9800"), (200, "#9c27b0")]


def _win(df: pd.DataFrame) -> pd.DataFrame:
    return df.iloc[-WINDOW:] if len(df) > WINDOW else df


def _points(series: pd.Series) -> list[RegimePoint]:
    return [
        RegimePoint(ts=pd.Timestamp(ts).to_pydatetime(), value=round(float(v), 4))
        for ts, v in series.items()
        if pd.notna(v)
    ]


def _candles(df: pd.DataFrame) -> list[RegimeCandle]:
    return [
        RegimeCandle(
            ts=pd.Timestamp(ts).to_pydatetime(),
            open=round(float(r.open), 4),
            high=round(float(r.high), 4),
            low=round(float(r.low), 4),
            close=round(float(r.close), 4),
        )
        for ts, r in df.iterrows()
    ]


def _pick(frames: dict[str, pd.DataFrame], *cands: str) -> str | None:
    for c in cands:
        if c in frames and len(frames[c]) > 5:
            return c
    return None


def _index_chart(
    frames: dict[str, pd.DataFrame], sym: str, key: str, title: str, *, markers: bool = False
) -> RegimeChart | None:
    if sym not in frames or len(frames[sym]) == 0:
        return None
    full = frames[sym]
    w = _win(full)
    series = [RegimeSeries(label="price", kind="candle", candles=_candles(w))]
    for length, color in _MA:
        if len(full) >= length:
            ma = sma(full["close"], length).reindex(w.index)
            series.append(RegimeSeries(label=f"SMA{length}", kind="line", color=color,
                                       points=_points(ma)))
    marks: list[ChartMarker] = []
    if markers:
        start = w.index[0]
        for dt in M.distribution_days(full).dates:
            if pd.Timestamp(dt) >= start:
                marks.append(ChartMarker(ts=dt, label="D", color="#f23645",
                                         position="aboveBar", shape="arrowDown"))
        ftd = M.follow_through_day(full)
        if ftd.found and ftd.ts is not None and pd.Timestamp(ftd.ts) >= start:
            marks.append(ChartMarker(ts=ftd.ts, label="FTD", color="#089981",
                                     position="belowBar", shape="arrowUp"))
    return RegimeChart(key=key, title=title, pillar_key="primary_trend", series=series,
                       markers=marks)


def _candle_chart(
    frames: dict[str, pd.DataFrame], sym: str, key: str, title: str, pillar: str
) -> RegimeChart | None:
    """Single-asset price chart as candlesticks (preferred over a line for prices)."""
    if sym not in frames or len(frames[sym]) == 0:
        return None
    w = _win(frames[sym])
    return RegimeChart(
        key=key, title=title, pillar_key=pillar,
        series=[RegimeSeries(label="price", kind="candle", candles=_candles(w))],
    )


def _ratio_chart(
    frames: dict[str, pd.DataFrame], a: str, b: str, key: str, title: str, pillar: str,
    color: str = "#7e57c2"
) -> RegimeChart | None:
    if a not in frames or b not in frames:
        return None
    left, right = frames[a]["close"].align(frames[b]["close"], join="inner")
    ratio = (left / right).dropna()
    if len(ratio) == 0:
        return None
    w = ratio.iloc[-WINDOW:] if len(ratio) > WINDOW else ratio
    return RegimeChart(
        key=key, title=title, pillar_key=pillar,
        series=[RegimeSeries(label=f"{a}/{b}", kind="line", color=color, points=_points(w))],
        note="Relative strength (ratio of adjusted closes).",
    )


def build_charts(frames: dict[str, pd.DataFrame]) -> list[RegimeChart]:
    """Every chart the dashboard draws, from the loaded frames. Missing symbols skip."""
    out: list[RegimeChart | None] = [
        _index_chart(frames, U.SP500, "spx", "S&P 500 — daily (50/150/200 MA, distribution/FTD)",
                     markers=True),
        _index_chart(frames, U.NASDAQ, "nasdaq", "Nasdaq Composite — daily (50/150/200 MA)"),
        _ratio_chart(frames, U.RSP, U.SPY, "rsp_spy",
                     "Breadth: equal-weight vs cap-weight (RSP/SPY)", "breadth", "#089981"),
        _candle_chart(frames, _pick(frames, U.DXY, "DX=F", "UUP") or U.DXY, "dxy",
                      "US Dollar Index (DXY)", "intermarket"),
        _ratio_chart(frames, U.HIGH_YIELD, U.IG_CREDIT, "credit",
                     "Credit risk appetite (HYG/LQD)", "intermarket", "#00897b"),
        _ratio_chart(frames, U.SOFTWARE, U.SPY, "software",
                     "Liquidity proxy: software leadership (IGV/SPY)", "intermarket", "#3949ab"),
        _candle_chart(frames, U.VIX, "vix", "Volatility (VIX)", "volatility"),
    ]
    commodities = [
        (U.GOLD, "Gold"),
        (U.SILVER, "Silver"),
        (U.OIL, "Oil (WTI)"),
        (U.COPPER, "Copper"),
    ]
    for sym, name in commodities:
        chosen = _pick(frames, sym, U.COMMODITY_ETF[sym])
        if chosen:
            out.append(_candle_chart(frames, chosen, f"commodity_{sym}", name, "intermarket"))
    if _pick(frames, U.COPPER, U.COMMODITY_ETF[U.COPPER]) and _pick(
        frames, U.GOLD, U.COMMODITY_ETF[U.GOLD]
    ):
        out.append(
            _ratio_chart(
                frames,
                _pick(frames, U.COPPER, U.COMMODITY_ETF[U.COPPER]) or U.COPPER,
                _pick(frames, U.GOLD, U.COMMODITY_ETF[U.GOLD]) or U.GOLD,
                "copper_gold",
                "Copper/Gold (growth vs fear)",
                "intermarket",
                "#ef6c00",
            )
        )
    return [c for c in out if c is not None]
