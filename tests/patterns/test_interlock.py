"""Interlock: a bearish structure whose resistance caps a bullish target is flagged."""

from __future__ import annotations

from datetime import datetime

from ta_assistant.patterns.assemble import assign_conflicts
from ta_assistant.synthesis.schema import DetectedPattern, PatternStatus, Timeframe


def _pattern(
    pid: str,
    direction: str,
    *,
    start: datetime,
    end: datetime,
    levels: dict[str, float],
    entry: float | None = None,
    target: float | None = None,
) -> DetectedPattern:
    return DetectedPattern(
        id=pid,
        pattern_type=("bull_flag" if direction == "bullish" else "double_top"),
        timeframe=Timeframe.DAILY,
        status=PatternStatus.CONFIRMED,
        geometry_confidence=0.7,
        confidence=0.7,
        direction=direction,
        levels=levels,
        region_start=start,
        region_end=end,
        entry=entry,
        target=target,
    )


def test_bearish_ceiling_caps_bullish_target() -> None:
    bull = _pattern(
        "b",
        "bullish",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 3, 1),
        levels={"breakout": 100, "target": 130, "stop": 90},
        entry=100,
        target=130,
    )
    bear = _pattern(  # breakdown 110 + height 15 -> ceiling (resistance) 125, between 100 and 130
        "r",
        "bearish",
        start=datetime(2024, 2, 1),
        end=datetime(2024, 4, 1),
        levels={"breakout": 110, "pattern_height": 15},
    )
    assign_conflicts([bull, bear])
    assert bear.id in bull.conflicts_with
    assert bull.id in bear.conflicts_with
    assert bull.caution is not None and "125" in bull.caution


def test_no_conflict_when_ceiling_above_target() -> None:
    bull = _pattern(
        "b",
        "bullish",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 3, 1),
        levels={"breakout": 100, "target": 130, "stop": 90},
        entry=100,
        target=130,
    )
    bear = _pattern(  # ceiling 145 -> above the bull target, not in the path
        "r",
        "bearish",
        start=datetime(2024, 2, 1),
        end=datetime(2024, 4, 1),
        levels={"breakout": 135, "pattern_height": 10},
    )
    assign_conflicts([bull, bear])
    assert bull.conflicts_with == []
    assert bull.caution is None


def test_no_conflict_when_regions_disjoint() -> None:
    bull = _pattern(
        "b",
        "bullish",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 2, 1),
        levels={"breakout": 100, "target": 130, "stop": 90},
        entry=100,
        target=130,
    )
    bear = _pattern(
        "r",
        "bearish",
        start=datetime(2024, 6, 1),
        end=datetime(2024, 8, 1),
        levels={"breakout": 110, "pattern_height": 15},
    )
    assign_conflicts([bull, bear])
    assert bull.conflicts_with == []
