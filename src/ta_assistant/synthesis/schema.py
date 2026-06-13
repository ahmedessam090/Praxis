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

    direction: str = "bullish"  # "bullish" (tradeable long) | "bearish" (context/warning)
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(
        default_factory=list
    )  # interlocking patterns (cross-direction)
    caution: str | None = None  # e.g. "upside capped near X by a forming H&S top"

    # consensus + presentation
    role: str = "considered"  # "primary" | "secondary" | "cap" | "considered"
    cluster_id: int | None = None  # candidates describing the same structure share one id
    label_override: str | None = None  # human-recognizable label from the vision consensus
    chart_png: str | None = None  # focused per-pattern static image

    llm_is_valid: bool | None = None
    llm_label: str | None = None
    llm_rationale: str | None = None
    notes: str = ""

    @property
    def display_label(self) -> str:
        """Human-facing name — the vision-consensus label if it relabelled, else geometry."""
        return self.label_override or self.pattern_type


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


class NoteSeverity(StrEnum):
    INFO = "info"
    CAUTION = "caution"
    WARNING = "warning"


class AnalyticalNote(BaseModel):
    key: str
    severity: NoteSeverity
    message: str


class IndicatorSnapshot(BaseModel):
    timeframe: Timeframe
    close: float
    sma50: float | None = None
    sma150: float | None = None
    sma200: float | None = None
    ema21: float | None = None
    rsi14: float | None = None
    atr_pct: float | None = None
    realized_vol: float | None = None
    rel_volume: float | None = None
    avg_dollar_volume_20: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    pct_from_52w_high: float | None = None
    pct_above_sma50: float | None = None
    trend_template_pass: bool | None = None


class TickerAnalysis(BaseModel):
    schema_version: int = 2
    symbol: str
    generated_at: datetime
    timeframes: list[Timeframe] = Field(default_factory=list)
    summary: AnalysisSummary
    patterns: list[DetectedPattern] = Field(default_factory=list)
    charts: list[ChartArtifact] = Field(default_factory=list)
    notes: list[AnalyticalNote] = Field(default_factory=list)
    indicators: list[IndicatorSnapshot] = Field(default_factory=list)

    def patterns_for(self, tf: Timeframe) -> list[DetectedPattern]:
        return [p for p in self.patterns if p.timeframe == tf]

    def surfaced_for(self, tf: Timeframe) -> list[DetectedPattern]:
        """The 1-3 consensus patterns to actually draw/show for a timeframe."""
        order = {"primary": 0, "secondary": 1, "cap": 2}
        chosen = [p for p in self.patterns_for(tf) if p.role in order]
        return sorted(chosen, key=lambda p: order.get(p.role, 9))

    def considered_for(self, tf: Timeframe) -> list[DetectedPattern]:
        """Everything the engine found but consensus did not surface (collapsed in the UI)."""
        return [p for p in self.patterns_for(tf) if p.role == "considered"]

    def by_id(self, pattern_id: str | None) -> DetectedPattern | None:
        if pattern_id is None:
            return None
        return next((p for p in self.patterns if p.id == pattern_id), None)
