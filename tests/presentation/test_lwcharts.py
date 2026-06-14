"""lightweight-charts HTML builder: payload shape + offline inlining (string assertions)."""

from __future__ import annotations

from synth import ascending_triangle_df

from ta_assistant.presentation.lwcharts import build_lwc_html, build_payload
from ta_assistant.synthesis.schema import (
    PatternStatus,
    PriceNote,
    Shape,
    ShapeKind,
    ShapePoint,
    Timeframe,
    TimeframeThesis,
)


def _thesis(df) -> TimeframeThesis:  # type: ignore[no-untyped-def]
    ts0 = df.index[5].to_pydatetime()
    ts1 = df.index[-3].to_pydatetime()
    return TimeframeThesis(
        timeframe=Timeframe.DAILY,
        pattern_label="ascending triangle",
        status=PatternStatus.FORMING,
        confidence=0.8,
        breakout=100.0,
        target=115.0,
        stop=92.0,
        shapes=[
            Shape(
                kind=ShapeKind.TRENDLINE,
                points=[ShapePoint(ts=ts0, price=100.0), ShapePoint(ts=ts1, price=100.0)],
                role="resistance",
            ),
            Shape(
                kind=ShapeKind.MARKER,
                points=[ShapePoint(ts=ts0, price=80.0)],
                role="support",
                label="L1",
            ),
        ],
        price_notes=[
            PriceNote(price=115.0, label="Target 115", kind="target"),
            PriceNote(price=92.0, label="Stop 92", kind="stop"),
        ],
    )


def test_payload_shape() -> None:
    df = ascending_triangle_df()
    p = build_payload(df, _thesis(df), visible_bars=40)
    assert p["candles"] and {"time", "open", "high", "low", "close"} <= p["candles"][0].keys()
    assert len(p["lines"]) == 1  # the trendline
    assert len(p["priceLines"]) == 2  # the two price notes
    assert len(p["markers"]) == 1
    # times are UNIX seconds (so weekly/monthly bars slot by data point, not calendar day)
    t0 = p["candles"][0]["time"]
    assert isinstance(t0, int) and 1_000_000_000 < t0 < 2_000_000_000  # ~2001..2033, seconds


def test_build_lwc_html_inlines_library_offline() -> None:
    df = ascending_triangle_df()
    html = build_lwc_html(df, _thesis(df), title="ERO — daily", visible_bars=40)
    # the vendored library is inlined (offline) — no external <script src=...> tag
    assert "Lightweight Charts" in html
    assert "<script src" not in html.lower()
    assert "createChart" in html and "CandlestickSeries" in html
    assert "createPriceLine" in html
    assert "ERO — daily" in html


def test_no_thesis_still_renders_candles() -> None:
    df = ascending_triangle_df()
    p = build_payload(df, None, visible_bars=40)
    assert p["candles"] and not p["lines"] and not p["priceLines"]
