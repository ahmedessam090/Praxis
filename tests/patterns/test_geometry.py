"""Geometry primitives: ZigZag pivots, trendline fit, indicators."""

from __future__ import annotations

import pytest
from synth import ohlcv_from_close, zigzag_closes

from ta_assistant.patterns.indicators import atr, obv
from ta_assistant.patterns.pivots import atr_zigzag
from ta_assistant.patterns.trendlines import (
    count_touches,
    fit_trendline,
    line_fit_quality,
    line_is_legit,
)
from ta_assistant.patterns.types import Pivot


def test_zigzag_finds_alternating_swings() -> None:
    # Path: low 100 -> high 120 -> low 90 -> high 130 -> low 95
    closes = zigzag_closes([100, 120, 90, 130, 95], steps_per_leg=10)
    df = ohlcv_from_close(closes)
    pivots = atr_zigzag(df)

    kinds = [p.kind for p in pivots]
    prices = [round(p.price) for p in pivots]

    assert kinds == ["L", "H", "L", "H", "L"]
    assert prices == [100, 120, 90, 130, 95]
    assert pivots[-1].provisional is True
    assert all(not p.provisional for p in pivots[:-1])
    # pivot indices land on the actual extremes (legs of 10 bars)
    assert [p.idx for p in pivots] == [0, 10, 20, 30, 40]


def test_zigzag_ignores_noise_below_threshold() -> None:
    # Tiny oscillations around 100 should not produce swing pivots.
    closes = zigzag_closes([100, 100.5, 99.7, 100.4, 99.8], steps_per_leg=8)
    pivots = atr_zigzag(ohlcv_from_close(closes), min_pct=0.03)
    # at most the single provisional leg endpoint, no confirmed swings
    assert len([p for p in pivots if not p.provisional]) == 0


def test_fit_trendline_recovers_slope_intercept() -> None:
    line = fit_trendline([0, 1, 2, 3, 4], [1, 3, 5, 7, 9])  # y = 2x + 1
    assert line.slope == pytest.approx(2.0, abs=1e-9)
    assert line.intercept == pytest.approx(1.0, abs=1e-9)
    assert line.value_at(10) == pytest.approx(21.0, abs=1e-9)


def test_count_touches_within_tolerance() -> None:
    from datetime import datetime

    line = fit_trendline([0, 10], [100.0, 100.0])  # flat at 100
    pivots = [
        Pivot(idx=0, ts=datetime(2020, 1, 1), price=100.2, kind="H"),
        Pivot(idx=5, ts=datetime(2020, 1, 8), price=99.9, kind="H"),
        Pivot(idx=9, ts=datetime(2020, 1, 14), price=104.0, kind="H"),  # outside tol
    ]
    assert count_touches(line, pivots, tol=0.5) == 2


def test_line_fit_quality_reports_touches_and_residual() -> None:
    from datetime import datetime

    line = fit_trendline([0, 10], [100.0, 100.0])  # flat at 100
    pivots = [
        Pivot(idx=0, ts=datetime(2020, 1, 1), price=100.2, kind="H"),
        Pivot(idx=5, ts=datetime(2020, 1, 8), price=99.9, kind="H"),
        Pivot(idx=9, ts=datetime(2020, 1, 14), price=104.0, kind="H"),  # outside tol
    ]
    touches, residual = line_fit_quality(line, pivots, tol=0.5)
    assert touches == 2
    assert residual == pytest.approx(0.2, abs=1e-9)  # worst residual among the touches


def test_line_fit_quality_no_touches_is_inf() -> None:
    from datetime import datetime

    line = fit_trendline([0, 10], [100.0, 100.0])
    far = [Pivot(idx=0, ts=datetime(2020, 1, 1), price=130.0, kind="H")]
    touches, residual = line_fit_quality(line, far, tol=0.5)
    assert touches == 0 and residual == float("inf")


def test_line_is_legit_requires_min_touches() -> None:
    from datetime import datetime

    line = fit_trendline([0, 10], [100.0, 100.0])
    two_on = [
        Pivot(idx=0, ts=datetime(2020, 1, 1), price=100.1, kind="H"),
        Pivot(idx=5, ts=datetime(2020, 1, 8), price=99.95, kind="H"),
    ]
    assert line_is_legit(line, two_on, tol=0.5, min_touches=2) is True
    assert line_is_legit(line, two_on[:1], tol=0.5, min_touches=2) is False


def test_neckline_is_flat() -> None:
    from ta_assistant.patterns.detectors.base import neckline_is_flat

    flat = fit_trendline([0, 50], [100.0, 100.5])  # 0.5% rise over the span -> near-horizontal
    steep = fit_trendline([0, 50], [100.0, 120.0])  # 20% rise -> a sloped line, not a neckline
    assert neckline_is_flat(flat, 0, 50, 100.0) is True
    assert neckline_is_flat(steep, 0, 50, 100.0) is False


def test_rail_is_clean_rejects_scattered() -> None:
    from datetime import datetime

    from ta_assistant.patterns.detectors.base import rail_is_clean

    def _p(idx: int, price: float) -> Pivot:
        return Pivot(idx=idx, ts=datetime(2020, 1, 1), price=price, kind="H")

    clean_pts = [_p(0, 100.0), _p(15, 100.2), _p(30, 99.9)]  # all sit on a ~flat line
    clean_line = fit_trendline([p.idx for p in clean_pts], [p.price for p in clean_pts])
    assert rail_is_clean(clean_line, clean_pts, atr=1.0) is True

    zig_pts = [_p(0, 100.0), _p(10, 110.0), _p(20, 100.0), _p(30, 110.0)]  # no line fits these
    zig_line = fit_trendline([p.idx for p in zig_pts], [p.price for p in zig_pts])
    assert rail_is_clean(zig_line, zig_pts, atr=1.0) is False  # 0 touches within 0.6*ATR


def test_fit_confidence_rewards_tight_fit() -> None:
    from ta_assistant.patterns.detectors.base import fit_confidence

    assert fit_confidence(touches=4, residual=0.1, atr=1.0) > fit_confidence(2, 1.4, 1.0)
    assert fit_confidence(2, float("inf"), 1.0) == 0.5  # no touches -> neutral fallback


def test_indicators_basic() -> None:
    closes = list(range(1, 21))
    df = ohlcv_from_close([float(c) for c in closes], band=0.5)
    assert (atr(df, 14) > 0).all()
    # rising closes -> OBV strictly accumulating
    assert obv(df).iloc[-1] > obv(df).iloc[0]
