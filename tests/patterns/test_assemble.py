"""Candidate -> schema conversion (entry/target/RR) + nesting + JSON round-trip."""

from __future__ import annotations

from datetime import datetime, timedelta

from synth import double_bottom_df

from ta_assistant.patterns.assemble import assign_nesting, to_detected_pattern
from ta_assistant.patterns.context import build_context
from ta_assistant.patterns.detectors import detect_all
from ta_assistant.synthesis.schema import (
    AnalysisSummary,
    Bias,
    DetectedPattern,
    PatternStatus,
    TickerAnalysis,
    Timeframe,
)


def test_candidate_converts_with_rr_and_roundtrips() -> None:
    df = double_bottom_df()
    ctx = build_context(df, "daily")
    cand = next(c for c in detect_all(ctx) if c.pattern_type == "double_bottom")
    pat = to_detected_pattern(cand, "p1", df.index)

    assert pat.entry == cand.levels["breakout"]
    assert pat.target == cand.levels["target"]
    assert pat.rr_ratio is not None and pat.rr_ratio > 0
    assert pat.region_start < pat.region_end

    # full analysis round-trips through pydantic JSON (the Temporal/UI boundary)
    analysis = TickerAnalysis(
        symbol="TEST",
        generated_at=datetime(2024, 1, 1),
        timeframes=[Timeframe.DAILY],
        summary=AnalysisSummary(overall_bias=Bias.BULLISH, headline="x", price_now=130.0),
        patterns=[pat],
    )
    restored = TickerAnalysis.model_validate_json(analysis.model_dump_json())
    assert restored.patterns[0].pattern_type == "double_bottom"
    assert restored.patterns[0].timeframe == Timeframe.DAILY


def _pattern(pid: str, start: datetime, end: datetime, tf: Timeframe) -> DetectedPattern:
    return DetectedPattern(
        id=pid,
        pattern_type="x",
        timeframe=tf,
        status=PatternStatus.CONFIRMED,
        geometry_confidence=0.7,
        confidence=0.7,
        region_start=start,
        region_end=end,
    )


def test_nesting_attaches_child_to_smallest_enclosing_parent() -> None:
    base = datetime(2020, 1, 1)
    monthly = _pattern("m", base, base + timedelta(days=1000), Timeframe.MONTHLY)
    weekly = _pattern("w", base + timedelta(days=100), base + timedelta(days=400), Timeframe.WEEKLY)
    daily = _pattern("d", base + timedelta(days=300), base + timedelta(days=360), Timeframe.DAILY)

    assign_nesting([monthly, weekly, daily])

    assert daily.parent_id == "w"  # smallest enclosing
    assert weekly.parent_id == "m"
    assert monthly.parent_id is None
    assert "d" in weekly.child_ids
    assert "w" in monthly.child_ids
