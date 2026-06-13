"""Convert deterministic PatternCandidates into the public schema + assign nesting."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast

import pandas as pd

from ta_assistant.patterns.detectors.base import PatternCandidate
from ta_assistant.synthesis.schema import (
    DetectedPattern,
    PatternStatus,
    PivotPoint,
    Timeframe,
)


def _ts(index: pd.Index, idx: int) -> datetime:
    pos = max(0, min(int(idx), len(index) - 1))
    return cast(datetime, pd.Timestamp(index[pos]).to_pydatetime())


def to_detected_pattern(
    cand: PatternCandidate, pattern_id: str, index: pd.Index
) -> DetectedPattern:
    entry = cand.levels.get("breakout")
    stop = cand.levels.get("stop")
    target = cand.levels.get("target")
    rr: float | None = None
    if entry is not None and stop is not None and target is not None and entry > stop:
        rr = (target - entry) / (entry - stop)

    return DetectedPattern(
        id=pattern_id,
        pattern_type=cand.pattern_type,
        timeframe=Timeframe(cand.timeframe),
        status=PatternStatus(cand.status),
        geometry_confidence=cand.geometry_confidence,
        confidence=cand.geometry_confidence,
        pivots=[
            PivotPoint(idx=p.idx, ts=p.ts, price=p.price, kind=p.kind, provisional=p.provisional)
            for p in cand.pivots
        ],
        levels=cand.levels,
        prior_resistance=cand.prior_resistance,
        volume=cand.volume,
        region_start=_ts(index, cand.region_start_idx),
        region_end=_ts(index, cand.region_end_idx),
        region_start_idx=int(cand.region_start_idx),
        region_end_idx=int(cand.region_end_idx),
        entry=entry,
        stop=stop,
        target=target,
        rr_ratio=rr,
        notes=cand.notes,
        direction=cand.direction,
        conflicts_with=list(cand.conflicts_with),
    )


def assign_nesting(patterns: Sequence[DetectedPattern]) -> None:
    """Attach each pattern to the smallest enclosing larger-span pattern (by time
    containment) — e.g. a daily flag nests inside a weekly/monthly base."""
    for child in patterns:
        child_span = child.region_end - child.region_start
        best_parent: DetectedPattern | None = None
        best_span = None
        for parent in patterns:
            if parent.id == child.id:
                continue
            parent_span = parent.region_end - parent.region_start
            if parent_span <= child_span:
                continue
            if parent.region_start <= child.region_start and child.region_end <= parent.region_end:
                if best_span is None or parent_span < best_span:
                    best_parent, best_span = parent, parent_span
        if best_parent is not None:
            child.parent_id = best_parent.id
            best_parent.child_ids.append(child.id)


def assign_conflicts(patterns: Sequence[DetectedPattern]) -> None:
    """Flag interlock: a bearish structure whose resistance caps a bullish target.
    Sets conflicts_with both ways and a `caution` on the bullish pattern."""
    bulls = [p for p in patterns if p.direction == "bullish"]
    bears = [p for p in patterns if p.direction == "bearish"]
    for bull in bulls:
        if bull.target is None or bull.entry is None:
            continue
        for bear in bears:
            # regions must overlap in time
            if not (bull.region_start <= bear.region_end and bear.region_start <= bull.region_end):
                continue
            breakdown = bear.levels.get("breakout")
            height = bear.levels.get("pattern_height")
            if breakdown is None or height is None:
                continue
            ceiling = breakdown + height  # upper extent (resistance) of the bearish structure
            # the bull would have to push through that ceiling on its way to target
            if bull.entry < ceiling <= bull.target:
                if bear.id not in bull.conflicts_with:
                    bull.conflicts_with.append(bear.id)
                if bull.id not in bear.conflicts_with:
                    bear.conflicts_with.append(bull.id)
                bull.caution = (
                    f"upside likely capped near {ceiling:.2f} by a "
                    f"{bear.pattern_type} ({bear.status.value})"
                )
