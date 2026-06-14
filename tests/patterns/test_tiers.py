"""Pattern tiers: rounding bottom + double/triple bottoms are SUPPORT (context, not the
trade), and the consensus never makes a support pattern the primary."""

from __future__ import annotations

from synth import double_bottom_df, rounding_bottom_df, triple_bottom_df

from ta_assistant.patterns.context import build_context
from ta_assistant.patterns.detectors import double_bottom, rounding_bottom, triple_bottom
from ta_assistant.patterns.detectors.base import sane_levels


def test_rounding_bottom_detects_saucer_as_support() -> None:
    ctx = build_context(rounding_bottom_df(), "monthly")
    cands = rounding_bottom.detect(ctx)
    assert cands, "rounding bottom should fire on a clean multi-year saucer"
    c = cands[0]
    assert c.pattern_type == "rounding_bottom"
    assert c.tier == "support"
    assert sane_levels(c, ctx.last_close)
    assert len(c.pivots) >= 3 and all(p.kind == "C" for p in c.pivots)  # curve sample points


def test_rounding_bottom_ignores_a_dome() -> None:
    # an inverted (concave) parabola is a top, not a saucer -> must NOT fire
    from synth import ohlcv_from_close

    n = 61
    closes = [100.0 - (i - n / 2.0) ** 2 * (60.0 / (n / 2.0) ** 2) for i in range(n)]
    ctx = build_context(ohlcv_from_close(closes, band=1.0), "monthly")
    assert rounding_bottom.detect(ctx) == []


def test_double_and_triple_bottom_are_support() -> None:
    db = double_bottom.detect(build_context(double_bottom_df(), "daily"))
    tb = triple_bottom.detect(build_context(triple_bottom_df(), "daily"))
    assert db and db[0].tier == "support"
    assert tb and tb[0].tier == "support"
