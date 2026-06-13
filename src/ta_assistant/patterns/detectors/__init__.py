"""Pattern detectors (LONG-biased). Each returns candidate patterns with exact levels."""

from __future__ import annotations

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors import (
    ascending_triangle,
    bull_flag,
    cup_handle,
    double_bottom,
    inverse_hns,
)
from ta_assistant.patterns.detectors.base import PatternCandidate, add_volume_features

DETECTORS = [
    inverse_hns,
    double_bottom,
    ascending_triangle,
    cup_handle,
    bull_flag,
]


def detect_all(ctx: GeometryContext) -> list[PatternCandidate]:
    candidates: list[PatternCandidate] = []
    for module in DETECTORS:
        for cand in module.detect(ctx):
            add_volume_features(ctx, cand)
            candidates.append(cand)
    return candidates


__all__ = ["DETECTORS", "PatternCandidate", "detect_all"]
