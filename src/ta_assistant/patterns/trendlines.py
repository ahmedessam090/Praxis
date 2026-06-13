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
