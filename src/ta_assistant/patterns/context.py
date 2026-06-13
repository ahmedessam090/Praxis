"""GeometryContext: bundles one timeframe's bars + computed pivots/ATR for detectors."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ta_assistant.patterns.indicators import atr as atr_fn
from ta_assistant.patterns.pivots import atr_zigzag
from ta_assistant.patterns.types import Pivot


@dataclass
class GeometryContext:
    df: pd.DataFrame
    pivots: list[Pivot]
    atr: pd.Series
    timeframe: str

    def atr_at(self, idx: int) -> float:
        value = float(self.atr.to_numpy(dtype=float)[idx])
        return value if value > 0 else 1e-9

    @property
    def last_close(self) -> float:
        return float(self.df["close"].to_numpy(dtype=float)[-1])


def build_context(
    df: pd.DataFrame,
    timeframe: str,
    atr_mult: float = 3.0,
    atr_len: int = 14,
    min_pct: float = 0.03,
) -> GeometryContext:
    return GeometryContext(
        df=df,
        pivots=atr_zigzag(df, atr_mult=atr_mult, atr_len=atr_len, min_pct=min_pct),
        atr=atr_fn(df, atr_len),
        timeframe=timeframe,
    )
