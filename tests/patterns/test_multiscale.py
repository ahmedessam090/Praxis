"""Multi-scale detection: a recent consolidation that the coarse full-window ATR-ZigZag
swallows into one leg is resolved by a finer pass over a recent sub-window. This is the
fix for the weekly/monthly going blind to the current tradeable structure."""

from __future__ import annotations

from synth import ohlcv_from_close, zigzag_closes

from ta_assistant.patterns.context import build_context
from ta_assistant.patterns.detectors import detect_all
from ta_assistant.patterns.detectors.base import sane_levels

_CONSOLIDATION = {
    "ascending_triangle",
    "rectangle",
    "double_bottom",
    "triple_bottom",
    "symmetrical_triangle",
    "cup_and_handle",
    "head_and_shoulders_bottom",
}


def _types(ctx_df, **kw) -> set[str]:  # type: ignore[no-untyped-def]
    ctx = build_context(ctx_df, "weekly", **kw)
    return {c.pattern_type for c in detect_all(ctx) if sane_levels(c, ctx.last_close)}


def test_fine_recent_pass_surfaces_consolidation_the_coarse_pass_misses() -> None:
    # A long multi-year advance 12 -> 100, then a recent base: rising lows 85 < 90 < 95
    # beneath flat resistance ~100 (a textbook ascending-triangle consolidation).
    big = zigzag_closes([12, 100], 220)
    recent = zigzag_closes([100, 85, 100, 90, 100, 95, 101], 11)
    df = ohlcv_from_close([*big, *recent], band=1.0)

    coarse = _types(df, atr_mult=3.0, min_pct=0.03)  # full-window, coarse pivots
    fine = _types(df.iloc[-90:], atr_mult=1.6, min_pct=0.018)  # recent sub-window, fine pivots

    # The coarse pass cannot see the recent consolidation; the fine pass resolves it.
    assert fine & _CONSOLIDATION
    assert (fine & _CONSOLIDATION) - coarse
