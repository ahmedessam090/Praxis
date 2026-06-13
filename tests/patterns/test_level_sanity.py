"""sane_levels rejects degenerate/absurd levels (root-cause guard for the -40 axis)."""

from __future__ import annotations

from synth import ohlcv_from_close, zigzag_closes

from ta_assistant.patterns.context import build_context
from ta_assistant.patterns.detectors import detect_all
from ta_assistant.patterns.detectors.base import (
    _NON_PRICE_LEVEL_KEYS,
    BEARISH,
    BULLISH,
    PatternCandidate,
    sane_levels,
)


def _cand(direction: str = BULLISH, **levels: float) -> PatternCandidate:
    return PatternCandidate(
        pattern_type="x",
        timeframe="daily",
        status="confirmed",
        geometry_confidence=0.6,
        pivots=[],
        levels=dict(levels),
        region_start_idx=0,
        region_end_idx=10,
        direction=direction,
    )


def test_accepts_normal_bullish() -> None:
    assert sane_levels(_cand(breakout=100, target=120, stop=90, pattern_height=20), 100.0)


def test_rejects_negative_stop() -> None:
    assert not sane_levels(_cand(breakout=5, target=8, stop=-3, pattern_height=3), 5.0)


def test_rejects_out_of_band_target() -> None:
    assert not sane_levels(_cand(breakout=100, target=500, stop=95, pattern_height=400), 100.0)


def test_rejects_bad_order() -> None:  # stop above breakout (bullish)
    assert not sane_levels(_cand(breakout=100, target=120, stop=110, pattern_height=20), 100.0)


def test_rejects_degenerate_rr() -> None:  # stop glued to breakout -> RR ~ huge
    assert not sane_levels(_cand(breakout=100, target=300, stop=99.9, pattern_height=200), 100.0)


def test_bearish_order() -> None:
    assert sane_levels(_cand(BEARISH, breakout=100, target=80, stop=110, pattern_height=20), 100.0)
    assert not sane_levels(
        _cand(BEARISH, breakout=100, target=120, stop=110, pattern_height=20), 100.0
    )


def test_no_degenerate_levels_survive_on_declining_penny() -> None:
    # 40 -> 5 decline within the window (the ABCL-like case) + a small recent base.
    closes = zigzag_closes([40, 8, 25, 5, 9, 6, 9], steps_per_leg=12)
    ctx = build_context(ohlcv_from_close(closes), "daily")
    lc = ctx.last_close
    survivors = [c for c in detect_all(ctx) if sane_levels(c, lc)]
    for c in survivors:
        for key, value in c.levels.items():
            if key in _NON_PRICE_LEVEL_KEYS:
                continue
            assert 0 < value <= 3.0 * lc, f"{c.pattern_type}.{key}={value} (last_close={lc})"
