"""v3 schema: thesis/shapes round-trip + back-compat with legacy v2 payloads."""

from __future__ import annotations

from datetime import datetime

from ta_assistant.synthesis.schema import (
    AnalysisSummary,
    Bias,
    PatternStatus,
    PriceNote,
    Shape,
    ShapeKind,
    ShapePoint,
    SynthesisRead,
    TickerAnalysis,
    Timeframe,
    TimeframeThesis,
)


def _thesis() -> TimeframeThesis:
    return TimeframeThesis(
        timeframe=Timeframe.WEEKLY,
        pattern_label="ascending triangle",
        status=PatternStatus.FORMING,
        confidence=0.82,
        breakout=33.0,
        target=40.0,
        stop=25.0,
        shapes=[
            Shape(
                kind=ShapeKind.TRENDLINE,
                points=[
                    ShapePoint(ts=datetime(2026, 1, 1), price=33.0),
                    ShapePoint(ts=datetime(2026, 6, 1), price=33.0),
                ],
                role="resistance",
            )
        ],
        price_notes=[PriceNote(price=40.0, label="Target 40 (measured move)", kind="target")],
        rationale="flat resistance ~33, rising lows",
        seed_pattern_ids=["w5"],
    )


def test_thesis_round_trip() -> None:
    a = TickerAnalysis(
        symbol="ERO",
        generated_at=datetime(2026, 6, 13),
        timeframes=[Timeframe.WEEKLY],
        summary=AnalysisSummary(overall_bias=Bias.BULLISH, headline="x", price_now=29.4),
        theses=[_thesis()],
        synthesis=SynthesisRead(
            overall_bias=Bias.BULLISH, headline="hi", primary_timeframe=Timeframe.WEEKLY
        ),
    )
    b = TickerAnalysis.model_validate_json(a.model_dump_json())
    assert b.schema_version == 3
    t = b.thesis_for(Timeframe.WEEKLY)
    assert t is not None and t.pattern_label == "ascending triangle"
    assert t.shapes[0].kind == ShapeKind.TRENDLINE
    assert b.synthesis is not None and b.synthesis.primary_timeframe == Timeframe.WEEKLY


def test_legacy_v2_payload_still_loads() -> None:
    # A pre-v3 payload (no theses/synthesis) must still validate; the new fields default.
    legacy = (
        '{"schema_version": 2, "symbol": "AAPL", "generated_at": "2026-06-13T00:00:00",'
        ' "timeframes": ["daily"], "summary": {"overall_bias": "bullish",'
        ' "headline": "h", "price_now": 100.0}, "patterns": [], "charts": [],'
        ' "notes": [], "indicators": []}'
    )
    a = TickerAnalysis.model_validate_json(legacy)
    assert a.theses == []
    assert a.synthesis is None
    assert a.thesis_for(Timeframe.DAILY) is None
