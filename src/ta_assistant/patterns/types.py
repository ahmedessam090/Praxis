"""Shared geometry primitives (internal to the engine; the public output schema
lives in ta_assistant.synthesis.schema)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Pivot:
    """A significant swing point. `idx` is the positional index into the bars."""

    idx: int
    ts: datetime
    price: float
    kind: str  # "H" (swing high) | "L" (swing low)
    provisional: bool = False


@dataclass(frozen=True)
class Trendline:
    """price = slope * x + intercept, where x is the positional bar index."""

    slope: float
    intercept: float
    touch_idx: tuple[int, ...]

    def value_at(self, x: float) -> float:
        return self.slope * x + self.intercept
