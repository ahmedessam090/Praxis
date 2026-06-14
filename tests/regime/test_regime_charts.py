"""P5: the RegimeChart series builder + the offline lightweight-charts HTML renderer."""

from __future__ import annotations

import regime_synth as S

import ta_assistant.regime.universe as U
from ta_assistant.presentation.lwcharts import build_regime_chart_html, build_regime_payload
from ta_assistant.regime.charts import build_charts


def _frames() -> dict[str, object]:
    f: dict[str, object] = {
        U.SP500: S.distribution_heavy_on_uptrend(),  # gives distribution-day markers
        U.NASDAQ: S.bull_trend(),
        U.RSP: S.make_daily(S.linear(50.0, 0.5, 320)),
        U.SPY: S.make_daily(S.linear(400.0, 0.2, 320)),
        U.HIGH_YIELD: S.make_daily(S.linear(75.0, 0.1, 320)),
        U.IG_CREDIT: S.make_daily([110.0] * 320),
        U.SOFTWARE: S.make_daily(S.linear(80.0, 0.3, 320)),
        U.VIX: S.make_daily(S.linear(18.0, -0.01, 320)),
        U.COMMODITY_ETF[U.GOLD]: S.make_daily(S.linear(180.0, 0.05, 320)),  # GLD (ETF fallback)
    }
    return f


def test_build_charts_spx_has_candles_and_mas_and_markers() -> None:
    charts = build_charts(_frames())  # type: ignore[arg-type]
    spx = next(c for c in charts if c.key == "spx")
    assert spx.pillar_key == "primary_trend"
    kinds = {s.kind for s in spx.series}
    assert "candle" in kinds and "line" in kinds  # price + MAs
    assert any(s.label == "SMA200" for s in spx.series)
    assert len(spx.markers) >= 1  # distribution-day markers


def test_build_charts_includes_ratio_and_commodity() -> None:
    charts = build_charts(_frames())  # type: ignore[arg-type]
    keys = {c.key for c in charts}
    assert "rsp_spy" in keys  # breadth ratio
    assert "software" in keys  # liquidity proxy ratio
    assert "commodity_GC=F" in keys  # gold via the ETF fallback
    rsp = next(c for c in charts if c.key == "rsp_spy")
    assert rsp.pillar_key == "breadth"


def test_single_asset_prices_are_candles_ratios_are_lines() -> None:
    charts = {c.key: c for c in build_charts(_frames())}  # type: ignore[arg-type]
    # prices -> candlesticks (user preference)
    for key in ("vix", "commodity_GC=F"):
        assert charts[key].series[0].kind == "candle"
        assert charts[key].series[0].candles  # OHLC present
    # ratios -> lines (a ratio has no OHLC)
    for key in ("rsp_spy", "software", "credit"):
        assert charts[key].series[0].kind == "line"
        assert charts[key].series[0].points


def test_build_charts_windowed() -> None:
    # a long history is clipped to the ~2yr window
    long_frames = {U.SP500: S.make_daily(S.linear(50.0, 0.2, 900))}
    charts = build_charts(long_frames)  # type: ignore[arg-type]
    spx = next(c for c in charts if c.key == "spx")
    candle = next(s for s in spx.series if s.kind == "candle")
    assert len(candle.candles) <= 504


def test_regime_chart_html_offline_and_renders_series() -> None:
    charts = build_charts(_frames())  # type: ignore[arg-type]
    spx = next(c for c in charts if c.key == "spx")
    html = build_regime_chart_html(spx)
    assert "Lightweight Charts" in html  # vendored library inlined
    assert "<script src" not in html.lower()  # fully offline
    assert "createChart" in html and "CandlestickSeries" in html and "LineSeries" in html
    assert "createSeriesMarkers" in html
    # UNIX-seconds time in the payload (not date strings)
    payload = build_regime_payload(spx)
    t0 = payload["series"][0]["data"][0]["time"]
    assert isinstance(t0, int) and 1_000_000_000 < t0 < 2_000_000_000
