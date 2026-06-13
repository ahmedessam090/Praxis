"""Consensus: collapse redundant labels into one structure + pick primary/secondary/cap."""

from __future__ import annotations

from datetime import datetime

from ta_assistant.patterns.consensus import assign_consensus, cluster_candidates, pick_headline
from ta_assistant.synthesis.schema import DetectedPattern, PatternStatus, Timeframe


def _p(
    pid: str,
    ptype: str,
    *,
    tf: Timeframe = Timeframe.WEEKLY,
    direction: str = "bullish",
    status: PatternStatus = PatternStatus.FORMING,
    conf: float = 0.8,
    start: tuple[int, int, int] = (2026, 1, 1),
    end: tuple[int, int, int] = (2026, 6, 1),
    breakout: float = 100.0,
    target: float = 120.0,
    stop: float = 90.0,
    height: float = 20.0,
    conflicts_with: list[str] | None = None,
) -> DetectedPattern:
    return DetectedPattern(
        id=pid,
        pattern_type=ptype,
        timeframe=tf,
        status=status,
        geometry_confidence=conf,
        confidence=conf,
        direction=direction,
        levels={"breakout": breakout, "target": target, "stop": stop, "pattern_height": height},
        entry=breakout,
        target=target,
        stop=stop,
        region_start=datetime(*start),
        region_end=datetime(*end),
        conflicts_with=conflicts_with or [],
    )


def test_same_structure_labels_cluster_into_one() -> None:
    # cup + double-bottom + triple-bottom describing the same ~100 breakout, overlapping.
    cup = _p("a", "cup_and_handle", start=(2026, 1, 1), end=(2026, 6, 1), breakout=100, conf=0.99)
    db = _p("b", "double_bottom", start=(2026, 4, 1), end=(2026, 6, 1), breakout=101, conf=0.9)
    tb = _p("c", "triple_bottom", start=(2026, 3, 1), end=(2026, 6, 1), breakout=99.5, conf=0.85)
    assert len(cluster_candidates([cup, db, tb])) == 1


def test_far_breakout_does_not_cluster() -> None:
    a = _p("a", "cup_and_handle", breakout=100)
    b = _p("b", "double_bottom", breakout=140)  # ~40% away — a different structure
    assert len(cluster_candidates([a, b])) == 2


def test_disjoint_regions_do_not_cluster() -> None:
    a = _p("a", "cup_and_handle", start=(2026, 1, 1), end=(2026, 2, 1), breakout=100)
    b = _p("b", "double_bottom", start=(2026, 5, 1), end=(2026, 6, 1), breakout=100)
    assert len(cluster_candidates([a, b])) == 2


def test_cross_direction_never_clusters() -> None:
    bull = _p("a", "cup_and_handle", direction="bullish", breakout=100)
    bear = _p("b", "double_top", direction="bearish", breakout=100)
    assert len(cluster_candidates([bull, bear])) == 2


def test_one_surfaced_per_cluster_and_bear_is_cap() -> None:
    cup = _p("a", "cup_and_handle", breakout=100, conf=0.99)
    db = _p("b", "double_bottom", breakout=101, conf=0.9)
    bear = _p(
        "r",
        "double_top",
        direction="bearish",
        status=PatternStatus.CONFIRMED,
        breakout=80,
        target=60,
        stop=110,
        conf=0.7,
    )
    assign_consensus([cup, db, bear])
    assert cup.role == "primary"  # highest-confidence representative of the bullish cluster
    assert db.role == "considered"  # redundant label collapsed
    assert bear.role == "cap"


def test_secondary_prefers_a_continuation() -> None:
    primary = _p("a", "cup_and_handle", end=(2026, 6, 1), breakout=200, conf=0.9)
    # distinct breakout so it forms its own cluster; bull_flag is a continuation -> secondary
    flag = _p("f", "bull_flag", start=(2026, 5, 1), end=(2026, 6, 1), breakout=240, conf=0.6)
    assign_consensus([primary, flag])
    assert primary.role == "primary"
    assert flag.role == "secondary"


def test_interlocking_bearish_becomes_cap() -> None:
    primary = _p("a", "cup_and_handle", breakout=100, conf=0.9, conflicts_with=["r"])
    cap = _p("r", "head_and_shoulders_top", direction="bearish", breakout=80, conf=0.6)
    # a distinct, higher-confidence bear that does NOT interlock with primary
    decoy = _p("z", "double_top", direction="bearish", breakout=140, target=120, conf=0.95)
    assign_consensus([primary, cap, decoy])
    assert cap.role == "cap"  # the interlocking bear, not the higher-confidence decoy
    assert decoy.role == "considered"


def test_headline_prefers_weekly_over_stale_monthly() -> None:
    wk = _p("w", "cup_and_handle", tf=Timeframe.WEEKLY, conf=0.9, breakout=100)
    mo = _p(
        "m",
        "double_bottom",
        tf=Timeframe.MONTHLY,
        status=PatternStatus.TRIGGERED,  # triggered would win on status alone
        conf=0.8,
        breakout=50,
        target=70,
    )
    assign_consensus([wk, mo])
    head = pick_headline([wk, mo])
    assert head is not None and head.timeframe == Timeframe.WEEKLY
