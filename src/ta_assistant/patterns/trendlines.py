"""Robust trendline fitting (Theil–Sen) + touch counting."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy.stats import theilslopes

from ta_assistant.patterns.types import Pivot, Trendline


def fit_trendline(xs: Sequence[float], ys: Sequence[float]) -> Trendline:
    if len(xs) < 2:
        raise ValueError("need >= 2 points to fit a line")
    slope, intercept, _, _ = theilslopes(np.asarray(ys, dtype=float), np.asarray(xs, dtype=float))
    return Trendline(
        slope=float(slope), intercept=float(intercept), touch_idx=tuple(int(x) for x in xs)
    )


def count_touches(line: Trendline, pivots: Sequence[Pivot], tol: float) -> int:
    return sum(1 for p in pivots if abs(p.price - line.value_at(p.idx)) <= tol)


def line_fit_quality(line: Trendline, pivots: Sequence[Pivot], tol: float) -> tuple[int, float]:
    """How well a straight line is actually supported by the swings: the number of pivots that
    sit on it within `tol`, and the worst residual among those touches (so the caller can show
    "3 touches, within 0.4 of the line"). Residual is +inf when nothing touches."""
    residuals = [abs(p.price - line.value_at(p.idx)) for p in pivots]
    touching = [r for r in residuals if r <= tol]
    if not touching:
        return 0, float("inf")
    return len(touching), max(touching)


def line_is_legit(
    line: Trendline, pivots: Sequence[Pivot], tol: float, min_touches: int = 2
) -> bool:
    """A line you could actually draw by hand: at least `min_touches` pivots lie on it within
    `tol` (a point or two of deviation is fine — pass a generous tol for the hard reject)."""
    return count_touches(line, pivots, tol) >= min_touches
