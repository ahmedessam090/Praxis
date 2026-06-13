"""Bearish warning detectors fire with direction='bearish' and downward levels."""

from __future__ import annotations

import pytest
from synth import (
    bear_flag_df,
    descending_channel_df,
    descending_triangle_df,
    double_top_df,
    hns_top_df,
    ohlcv_from_close,
    rising_wedge_df,
    triple_top_df,
)

from ta_assistant.patterns.context import build_context
from ta_assistant.patterns.detectors import PatternCandidate, detect_all


def _find(cands: list[PatternCandidate], ptype: str) -> PatternCandidate | None:
    return next((c for c in cands if c.pattern_type == ptype), None)


def test_hns_top() -> None:
    c = _find(detect_all(build_context(hns_top_df(), "daily")), "head_and_shoulders_top")
    assert c is not None
    assert c.direction == "bearish"
    assert c.levels["head_high"] == pytest.approx(115, abs=3)
    assert c.levels["target"] < c.levels["breakout"]  # downside target


def test_double_top() -> None:
    c = _find(detect_all(build_context(double_top_df(), "daily")), "double_top")
    assert c is not None
    assert c.direction == "bearish"
    assert c.levels["neckline"] == pytest.approx(105, abs=3)
    assert c.levels["target"] == pytest.approx(90, abs=4)


def test_triple_top() -> None:
    c = _find(detect_all(build_context(triple_top_df(), "daily")), "triple_top")
    assert c is not None
    assert c.direction == "bearish"
    assert c.levels["neckline"] == pytest.approx(90, abs=3)


def test_descending_triangle() -> None:
    c = _find(detect_all(build_context(descending_triangle_df(), "daily")), "descending_triangle")
    assert c is not None
    assert c.direction == "bearish"
    assert c.levels["support"] == pytest.approx(70, abs=3)


def test_rising_wedge() -> None:
    c = _find(detect_all(build_context(rising_wedge_df(), "daily")), "rising_wedge")
    assert c is not None
    assert c.direction == "bearish"
    assert c.levels["target"] < c.levels["breakout"]


def test_descending_channel() -> None:
    c = _find(detect_all(build_context(descending_channel_df(), "daily")), "descending_channel")
    assert c is not None
    assert c.direction == "bearish"


def test_bear_flag() -> None:
    c = _find(detect_all(build_context(bear_flag_df(), "daily")), "bear_flag")
    assert c is not None
    assert c.direction == "bearish"
    assert c.levels["pattern_height"] == pytest.approx(30, abs=6)


def test_no_bearish_on_uptrend_noise() -> None:
    rising = [100 + i * 0.5 + (i % 2) * 0.2 for i in range(60)]
    cands = detect_all(build_context(ohlcv_from_close(rising), "daily"))
    assert _find(cands, "head_and_shoulders_top") is None
    assert _find(cands, "double_top") is None
