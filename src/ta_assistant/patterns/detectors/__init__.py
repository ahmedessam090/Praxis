"""Pattern detectors (LONG-biased). Each returns candidate patterns with exact levels."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors import (
    ascending_channel,
    ascending_triangle,
    bear_flag,
    bull_flag,
    cup_handle,
    descending_channel,
    descending_triangle,
    double_bottom,
    double_top,
    falling_wedge,
    hns_top,
    inverse_hns,
    rectangle,
    rising_wedge,
    rounding_bottom,
    symmetrical_triangle,
    triple_bottom,
    triple_top,
)
from ta_assistant.patterns.detectors.base import PatternCandidate, add_volume_features

DETECTORS = [
    # bullish (tradeable longs)
    inverse_hns,
    double_bottom,
    triple_bottom,
    ascending_triangle,
    symmetrical_triangle,
    falling_wedge,
    ascending_channel,
    rectangle,
    cup_handle,
    bull_flag,
    # support (context / confirmation — not standalone trades)
    rounding_bottom,
    # bearish (context / warnings, not short entries)
    hns_top,
    double_top,
    triple_top,
    descending_triangle,
    rising_wedge,
    descending_channel,
    bear_flag,
]


def detect_all(ctx: GeometryContext) -> list[PatternCandidate]:
    candidates: list[PatternCandidate] = []
    for module in DETECTORS:
        for cand in module.detect(ctx):
            add_volume_features(ctx, cand)
            candidates.append(cand)
    return candidates


__all__ = ["DETECTORS", "PatternCandidate", "detect_all"]
