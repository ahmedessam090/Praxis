"""Unit tests for the deterministic key-levels + chart-gap detector
(``ta_assistant.screener.levels``). Hand-built synthetic OHLCV frames keep the
expected classifications fully deterministic."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ta_assistant.screener import levels
from ta_assistant.synthesis.schema import GapNote, KeyLevel


def _frame(
    bars: Sequence[tuple[float, float, float, float, float]],
    *,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    """Build a daily OHLCV frame from (open, high, low, close, volume) tuples."""
    idx = pd.bdate_range(start=start, periods=len(bars), name="ts")
    return pd.DataFrame(
        {
            "open": [b[0] for b in bars],
            "high": [b[1] for b in bars],
            "low": [b[2] for b in bars],
            "close": [b[3] for b in bars],
            "volume": [b[4] for b in bars],
            "is_partial": [False] * len(bars),
        },
        index=idx,
    )


def _flat_bars(
    n: int, price: float, vol: float = 1_000_000.0
) -> list[tuple[float, float, float, float, float]]:
    """A tight, range-bound base around ``price``."""
    return [(price, price * 1.003, price * 0.997, price, vol) for _ in range(n)]


# --- gaps ---------------------------------------------------------------------


def test_breakaway_gap_up_detected() -> None:
    """A clear unfilled gap-up out of a tight base, on heavy volume, is surfaced and
    classified as a textbook (breakaway/runaway) gap — not suppressed."""
    bars = _flat_bars(40, 100.0)
    # Gap up from a ~100 base to ~110, on 3x volume, then drift higher (unfilled).
    bars.append((110.0, 111.0, 109.0, 110.5, 3_000_000.0))  # the gap bar
    for k in range(20):
        lvl = 111.0 + k * 0.4
        bars.append((lvl, lvl * 1.004, lvl * 0.998, lvl, 1_000_000.0))

    gaps = levels.detect_gaps(_frame(bars))

    assert gaps, "expected the gap-up to be detected"
    g = gaps[0]
    assert isinstance(g, GapNote)
    assert g.direction == "up"
    assert g.kind in {"breakaway", "runaway"}
    assert g.filled is False
    assert g.lower == 100.3 and g.upper == 109.0  # base top -> gap-bar low
    assert g.volume_ratio is not None and g.volume_ratio > 2.0
    assert g.note  # has a plain-English read


def test_tiny_in_range_gap_suppressed_as_common() -> None:
    """A tiny gap inside a tight congestion range that fills is a common gap and must
    NOT be returned."""
    bars = _flat_bars(30, 100.0)
    # Sub-1% gap up (100.3 base top -> 100.6) that fills immediately next bar.
    bars.append((100.6, 100.9, 100.6, 100.7, 1_000_000.0))  # tiny gap
    bars.append((100.4, 100.5, 100.1, 100.2, 1_000_000.0))  # trades back -> fills
    bars += _flat_bars(10, 100.0)

    gaps = levels.detect_gaps(_frame(bars))

    assert gaps == [], f"common gap should be suppressed, got {gaps}"


def test_exhaustion_gap_after_extended_run() -> None:
    """A gap-up far above the 50-bar MA that fills soon after reads as exhaustion."""
    bars: list[tuple[float, float, float, float, float]] = []
    lvl = 50.0
    for _ in range(60):  # long, steep advance -> price well above its 50-bar MA
        bars.append((lvl, lvl * 1.01, lvl * 0.995, lvl * 1.008, 1_000_000.0))
        lvl *= 1.02
    # Climactic gap up, then it reverses and fills.
    top = lvl
    bars.append((top * 1.06, top * 1.08, top * 1.05, top * 1.055, 4_000_000.0))
    for _ in range(8):
        bars.append((top * 0.99, top * 1.0, top * 0.95, top * 0.96, 1_500_000.0))

    gaps = levels.detect_gaps(_frame(bars))

    assert any(g.kind == "exhaustion" and g.filled for g in gaps)


# --- key levels ---------------------------------------------------------------


def test_key_levels_surfaces_52w_high_and_swing_resistance() -> None:
    """key_levels surfaces the 52-week high above price and a prior swing-high
    resistance above the current price."""
    bars: list[tuple[float, float, float, float, float]] = []
    # Rise to a swing-high peak at ~120, pull back, base near 105 (current price).
    up = list(range(100, 121))  # 100..120
    for p in up:
        bars.append((float(p), float(p) + 1.0, float(p) - 0.5, float(p), 1_000_000.0))
    for _ in range(20):  # tail down toward the pullback
        bars.append((118.0, 118.5, 110.0, 112.0, 1_000_000.0))
    # Settle into a base around 105 for the recent stretch.
    bars += _flat_bars(40, 105.0)

    lv = levels.key_levels(_frame(bars), max_levels=5)

    assert lv, "expected some key levels"
    assert all(isinstance(x, KeyLevel) for x in lv)
    kinds = {x.kind for x in lv}
    assert "52w_high" in kinds
    high_52 = next(x for x in lv if x.kind == "52w_high")
    assert high_52.price > 105.0  # above the ~105 current price
    assert high_52.distance_pct > 0  # signed positive (above price)
    # A prior swing-high pivot above price is surfaced as resistance.
    assert any(x.kind == "resistance" and x.price > 105.0 for x in lv)


def test_key_levels_distance_signs() -> None:
    """Levels above price are +%, supports below are -%."""
    bars: list[tuple[float, float, float, float, float]] = []
    for p in range(80, 131):  # climb to ~130
        bars.append((float(p), float(p) + 1.0, float(p) - 1.0, float(p), 1_000_000.0))
    bars += _flat_bars(30, 110.0)  # pull back to ~110, the current price

    lv = levels.key_levels(_frame(bars))

    for x in lv:
        if x.price > 110.0:
            assert x.distance_pct > 0
        elif x.price < 110.0:
            assert x.distance_pct < 0


# --- graceful degradation -----------------------------------------------------


def test_empty_input_returns_empty() -> None:
    empty = pd.DataFrame(
        columns=["open", "high", "low", "close", "volume", "is_partial"]
    )
    assert levels.key_levels(empty) == []
    assert levels.detect_gaps(empty) == []
    assert levels.attention(empty) == ([], [])


def test_short_input_returns_empty() -> None:
    bars = _flat_bars(3, 100.0)
    assert levels.key_levels(_frame(bars)) == []
    assert levels.detect_gaps(_frame(bars)) == []


def test_trailing_partial_bar_dropped() -> None:
    """The last bar is partial and must be excluded from analysis."""
    bars = _flat_bars(40, 100.0)
    bars.append((110.0, 111.0, 109.0, 110.5, 3_000_000.0))  # real gap bar
    df = _frame(bars)
    # Append a trailing partial bar that would otherwise be the current price.
    extra = _frame([(200.0, 201.0, 199.0, 200.0, 10.0)], start="2024-06-03")
    extra.loc[extra.index[-1], "is_partial"] = True
    df = pd.concat([df, extra])

    price = levels.key_levels(df)
    # Current price should be 110.5 (last non-partial close), not 200.
    # No level should sit at the partial bar's 200 print.
    assert all(abs(x.price - 200.0) > 1.0 for x in price)
