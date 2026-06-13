"""FRED macro-series provider (Phase 3 regime layer)."""

from __future__ import annotations


def get_series(series_id: str) -> list[tuple[str, float]]:
    """Fetch a FRED series (e.g. DGS2, DGS10, DCOILWTICO) as (date, value) pairs.

    Phase 1/3: import fredapi INSIDE this function.
    """
    raise NotImplementedError("Phase 1: wire fredapi here (import inside this function).")
