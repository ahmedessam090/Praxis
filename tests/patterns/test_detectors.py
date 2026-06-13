"""Each detector finds its synthetic pattern with correct level math."""

from __future__ import annotations

import pytest
from synth import (
    ascending_triangle_df,
    bull_flag_df,
    cup_handle_df,
    double_bottom_df,
    inverse_hns_df,
    ohlcv_from_close,
)

from ta_assistant.patterns.context import build_context
from ta_assistant.patterns.detectors import PatternCandidate, detect_all


def _find(cands: list[PatternCandidate], ptype: str) -> PatternCandidate | None:
    return next((c for c in cands if c.pattern_type == ptype), None)


def test_double_bottom_levels() -> None:
    c = _find(detect_all(build_context(double_bottom_df(), "daily")), "double_bottom")
    assert c is not None
    assert c.levels["neckline"] == pytest.approx(105, abs=2)
    assert c.levels["target"] == pytest.approx(120, abs=3)
    assert c.status == "triggered"


def test_inverse_hns_levels() -> None:
    c = _find(detect_all(build_context(inverse_hns_df(), "daily")), "head_and_shoulders_bottom")
    assert c is not None
    assert c.levels["head_low"] == pytest.approx(85, abs=2)
    assert c.levels["neckline"] == pytest.approx(103, abs=3)
    assert c.levels["target"] == pytest.approx(121, abs=4)


def test_ascending_triangle_levels() -> None:
    c = _find(detect_all(build_context(ascending_triangle_df(), "daily")), "ascending_triangle")
    assert c is not None
    assert c.levels["resistance"] == pytest.approx(100, abs=2)
    assert c.levels["target"] == pytest.approx(120, abs=4)


def test_cup_handle_levels() -> None:
    c = _find(detect_all(build_context(cup_handle_df(), "daily")), "cup_and_handle")
    assert c is not None
    assert c.levels["rim"] == pytest.approx(100, abs=3)
    assert c.levels["cup_bottom"] == pytest.approx(70, abs=3)
    assert c.levels["target"] == pytest.approx(130, abs=5)


def test_bull_flag_levels() -> None:
    c = _find(detect_all(build_context(bull_flag_df(), "daily")), "bull_flag")
    assert c is not None
    assert c.levels["pattern_height"] == pytest.approx(30, abs=4)
    assert c.levels["target"] == pytest.approx(110, abs=5)


def test_no_marquee_pattern_on_noise() -> None:
    flat = [100 + (i % 2) * 0.3 for i in range(60)]
    cands = detect_all(build_context(ohlcv_from_close(flat), "daily"))
    assert _find(cands, "head_and_shoulders_bottom") is None
