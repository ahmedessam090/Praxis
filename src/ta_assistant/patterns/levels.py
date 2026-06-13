"""Horizontal support/resistance clustering from pivot prices."""

from __future__ import annotations

from collections.abc import Sequence


def cluster_prices(prices: Sequence[float], tol: float) -> list[tuple[float, int]]:
    """Group nearby price levels. Returns (level_price, touch_count) sorted by
    touch_count desc then price. `tol` is the absolute price width of a cluster."""
    if not prices:
        return []
    ordered = sorted(prices)
    clusters: list[list[float]] = [[ordered[0]]]
    for price in ordered[1:]:
        if price - clusters[-1][-1] <= tol:
            clusters[-1].append(price)
        else:
            clusters.append([price])
    levels = [(sum(c) / len(c), len(c)) for c in clusters]
    return sorted(levels, key=lambda lv: (-lv[1], lv[0]))


def prior_resistance(
    levels: Sequence[tuple[float, int]], above: float, below: float | None = None
) -> list[float]:
    """Cluster levels lying above `above` (and optionally below `below`), nearest first."""
    out = [lv for lv, _ in levels if lv > above and (below is None or lv <= below)]
    return sorted(out)
