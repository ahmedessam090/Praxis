"""Indicator snapshot + analytical-note thresholds."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from ta_assistant.patterns.indicators import rsi
from ta_assistant.synthesis.notes import analyze_notes, snapshot
from ta_assistant.synthesis.schema import Timeframe


def _daily(
    closes: Sequence[float],
    volume: float = 2_000_000.0,
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
) -> pd.DataFrame:
    c = np.asarray(closes, dtype=float)
    idx = pd.bdate_range("2020-01-01", periods=len(c))
    return pd.DataFrame(
        {
            "open": c,
            "high": np.asarray(highs, float) if highs is not None else c + 0.5,
            "low": np.asarray(lows, float) if lows is not None else c - 0.5,
            "close": c,
            "volume": np.full(len(c), volume),
        },
        index=idx,
    )


def _notes(df: pd.DataFrame, earnings_days: int | None = None) -> list:
    return analyze_notes(df, {Timeframe.DAILY: snapshot(df, Timeframe.DAILY)}, [], earnings_days)


def test_rsi_bounds() -> None:
    assert rsi(pd.Series(range(1, 60), dtype=float)).iloc[-1] > 70
    assert rsi(pd.Series(range(60, 1, -1), dtype=float)).iloc[-1] < 30


def test_snapshot_fields() -> None:
    s = snapshot(_daily(list(range(1, 260))), Timeframe.DAILY)
    assert s.close == 259.0
    assert s.sma50 is not None and s.rsi14 is not None and s.high_52w is not None


def test_volatility_warning() -> None:
    notes = _notes(_daily([100.0] * 60, highs=[108.0] * 60, lows=[92.0] * 60))
    assert any(n.key == "volatility_high" and n.severity.value == "warning" for n in notes)


def test_liquidity_warning() -> None:
    notes = _notes(_daily([10.0] * 60, volume=1_000.0))
    assert any(n.key == "liquidity_thin" and n.severity.value == "warning" for n in notes)


def test_earnings_warning() -> None:
    notes = _notes(_daily([100.0] * 60), earnings_days=5)
    assert any(n.key == "earnings_soon" and n.severity.value == "warning" for n in notes)


def test_low_history_note() -> None:
    notes = _notes(_daily([100.0] * 40))
    assert any(n.key == "low_history" for n in notes)
