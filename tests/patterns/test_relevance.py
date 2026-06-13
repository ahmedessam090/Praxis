"""is_actionable keeps only currently-tradeable patterns."""

from __future__ import annotations

from ta_assistant.patterns.detectors.base import (
    BEARISH,
    BULLISH,
    CONFIRMED,
    FORMING,
    INVALIDATED,
    TRIGGERED,
    PatternCandidate,
    is_actionable,
)

CUTOFF = 90  # "recent" means idx >= 90


def _cand(
    status: str,
    *,
    direction: str = BULLISH,
    region_end_idx: int = 100,
    breakout_idx: int | None = None,
    **levels: float,
) -> PatternCandidate:
    return PatternCandidate(
        pattern_type="x",
        timeframe="daily",
        status=status,
        geometry_confidence=0.6,
        pivots=[],
        levels=dict(levels),
        region_start_idx=0,
        region_end_idx=region_end_idx,
        breakout_idx=breakout_idx,
        direction=direction,
    )


def test_invalidated_dropped() -> None:
    assert not is_actionable(_cand(INVALIDATED, breakout=100, target=120), 105, CUTOFF)


def test_stale_dropped() -> None:
    assert not is_actionable(
        _cand(CONFIRMED, region_end_idx=50, breakout=100, target=120), 95, CUTOFF
    )


def test_forming_kept_below_target() -> None:
    assert is_actionable(_cand(FORMING, breakout=100, target=120), 98, CUTOFF)


def test_forming_dropped_past_target() -> None:
    assert not is_actionable(_cand(CONFIRMED, breakout=100, target=120), 125, CUTOFF)


def test_triggered_kept_mid_move() -> None:
    assert is_actionable(_cand(TRIGGERED, breakout_idx=95, breakout=100, target=120), 110, CUTOFF)


def test_triggered_dropped_at_target() -> None:
    assert not is_actionable(
        _cand(TRIGGERED, breakout_idx=95, breakout=100, target=120), 121, CUTOFF
    )


def test_triggered_dropped_when_breakout_stale() -> None:
    assert not is_actionable(
        _cand(TRIGGERED, breakout_idx=60, breakout=100, target=120), 110, CUTOFF
    )


def test_bearish_forming_kept_above_target() -> None:
    assert is_actionable(_cand(FORMING, direction=BEARISH, breakout=100, target=80), 95, CUTOFF)


def test_bearish_triggered_dropped_when_played_out() -> None:
    c = _cand(TRIGGERED, direction=BEARISH, breakout_idx=95, breakout=100, target=80)
    assert not is_actionable(c, 78, CUTOFF)
