"""Public analysis output contract (pydantic v2).

This is what AnalyzeTickerWorkflow returns and the UI renders; it round-trips
through Temporal's pydantic data converter and is stored in Analysis.payload_json.
Kept import-light (no pandas/patterns imports) so it's cheap everywhere.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Timeframe(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class PatternStatus(StrEnum):
    FORMING = "forming"
    CONFIRMED = "confirmed"
    TRIGGERED = "triggered"
    INVALIDATED = "invalidated"


class Bias(StrEnum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


class PivotPoint(BaseModel):
    idx: int
    ts: datetime
    price: float
    kind: str  # "H" | "L"
    provisional: bool = False


class DetectedPattern(BaseModel):
    id: str
    pattern_type: str
    timeframe: Timeframe
    status: PatternStatus
    geometry_confidence: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)  # post-LLM (== geometry until validated)

    pivots: list[PivotPoint] = Field(default_factory=list)
    levels: dict[str, float] = Field(default_factory=dict)
    prior_resistance: list[float] = Field(default_factory=list)
    volume: dict[str, float] = Field(default_factory=dict)

    region_start: datetime
    region_end: datetime
    region_start_idx: int = 0  # positional (into the timeframe's bars) for charting
    region_end_idx: int = 0

    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rr_ratio: float | None = None

    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)

    llm_is_valid: bool | None = None
    llm_label: str | None = None
    llm_rationale: str | None = None
    notes: str = ""


class ChartArtifact(BaseModel):
    timeframe: Timeframe
    png_path: str
    pattern_ids: list[str] = Field(default_factory=list)


class AnalysisSummary(BaseModel):
    overall_bias: Bias
    headline: str
    price_now: float
    best_setup_id: str | None = None
    narrative: str | None = None


class TickerAnalysis(BaseModel):
    schema_version: int = 1
    symbol: str
    generated_at: datetime
    timeframes: list[Timeframe] = Field(default_factory=list)
    summary: AnalysisSummary
    patterns: list[DetectedPattern] = Field(default_factory=list)
    charts: list[ChartArtifact] = Field(default_factory=list)

    def patterns_for(self, tf: Timeframe) -> list[DetectedPattern]:
        return [p for p in self.patterns if p.timeframe == tf]
