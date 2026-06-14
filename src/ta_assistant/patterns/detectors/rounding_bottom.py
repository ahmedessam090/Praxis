"""Rounding bottom (saucer): a long, smooth U-shaped base — the big-picture reversal
STORY (often multi-year), not a standalone trade. Tagged SUPPORT: it strengthens a core
breakout setup rather than being traded on its own. Detected by fitting a convex (a>0)
parabola to closes and requiring a smooth fit with a roughly central low.
"""

from __future__ import annotations

import numpy as np

from ta_assistant.patterns.context import GeometryContext
from ta_assistant.patterns.detectors.base import SUPPORT, PatternCandidate, classify
from ta_assistant.patterns.types import Pivot

PATTERN_TYPE = "rounding_bottom"
_MIN_BARS = 40  # a saucer needs a long base


def detect(ctx: GeometryContext) -> list[PatternCandidate]:
    df = ctx.df
    n = len(df)
    if n < _MIN_BARS:
        return []
    closes = df["close"].to_numpy(dtype=float)
    if (closes <= 0).any():
        return []
    # Fit in LOG price — a multi-year saucer is a clean U on a log scale (equal % moves),
    # not on a linear scale where a late surge dominates and flattens the early base.
    x = np.arange(n, dtype=float)
    y = np.log(closes)
    a, b, c = (float(v) for v in np.polyfit(x, y, 2))
    if a <= 0:  # must be convex-up (a saucer), not a dome
        return []
    vertex = -b / (2 * a)
    if not (0.2 * n <= vertex <= 0.8 * n):  # the low must be roughly central
        return []
    fit = a * x * x + b * x + c
    ss_res = float(np.sum((y - fit) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r2 = 1.0 - ss_res / ss_tot
    if r2 < 0.5:  # a smooth saucer, not noise
        return []

    # rim = the pre-decline / left high the saucer must reclaim to complete
    rim = float(df["high"].to_numpy(dtype=float)[: max(1, n // 6)].max())
    low = float(df["low"].to_numpy(dtype=float).min())
    depth = rim - low
    if depth <= 0 or rim <= 0:
        return []
    stop = rim - 0.4 * depth
    uses_prov = bool(ctx.pivots and ctx.pivots[-1].provisional)
    status, breakout_idx = classify(ctx, n - 1, rim, stop, uses_prov)

    # sample the fitted (log) parabola as a smooth price curve for drawing ("C" = curve point)
    curve = [
        Pivot(
            idx=int(i),
            ts=df.index[int(i)].to_pydatetime(),
            price=float(np.exp(a * i * i + b * i + c)),
            kind="C",
        )
        for i in np.linspace(0, n - 1, 9).astype(int)
    ]
    return [
        PatternCandidate(
            pattern_type=PATTERN_TYPE,
            timeframe=ctx.timeframe,
            status=status,
            geometry_confidence=min(0.5 + 0.4 * r2, 0.9),
            pivots=curve,
            levels={
                "breakout": rim,
                "resistance": rim,
                "target": rim + depth,
                "stop": stop,
                "pattern_height": depth,
                "parabola_a": a,
                "parabola_b": b,
                "parabola_c": c,
            },
            region_start_idx=0,
            region_end_idx=n - 1,
            breakout_idx=breakout_idx,
            tier=SUPPORT,
        )
    ]
