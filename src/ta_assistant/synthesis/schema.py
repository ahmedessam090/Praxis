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
    tier: str = "core"  # "core" (tradeable) | "support" (context: rounding/double/triple bottom)
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


# --- AI analyst output (the chartist's thesis + what to draw) ---


class ShapeKind(StrEnum):
    TRENDLINE = "trendline"  # 2-point diagonal (resistance/support/neckline rail)
    CURVE = "curve"  # polyline through N points (H&S arc, cup)
    HLINE = "hline"  # horizontal level
    ZONE = "zone"  # filled price band (target box / supply zone): 2 points = band edges
    MARKER = "marker"  # labelled point(s) (LS/Head/RS, pivots)


class ShapePoint(BaseModel):
    ts: datetime
    price: float


class Shape(BaseModel):
    kind: ShapeKind
    points: list[ShapePoint] = Field(default_factory=list)
    label: str = ""
    # primary|secondary|cap|support|resistance|neckline|target|stop|entry
    role: str = "primary"
    color: str | None = None  # optional; renderer maps role->color when None


class PriceNote(BaseModel):
    price: float
    label: str  # e.g. "Breakout 152.30", "Target 178 (measured move)"
    kind: str  # entry|breakout|target|stop|level


class TimeframeThesis(BaseModel):
    """What the AI analyst concluded for ONE timeframe — its own pattern call, the exact
    levels (verified via the geometry tools), the shapes to draw, and an audit trail."""

    timeframe: Timeframe
    pattern_label: str  # the human name the analyst assigns
    status: PatternStatus = PatternStatus.FORMING
    direction: str = "bullish"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    entry: float | None = None
    breakout: float | None = None
    target: float | None = None
    target2: float | None = None
    stop: float | None = None
    rr_ratio: float | None = None

    shapes: list[Shape] = Field(default_factory=list)
    price_notes: list[PriceNote] = Field(default_factory=list)
    # Supporting (non-tradeable) structures that strengthen the core thesis — e.g. a
    # multi-year rounding bottom, a double/triple bottom at the base.
    supporting_factors: list[str] = Field(default_factory=list)
    rationale: str = ""
    transcript: list[str] = Field(default_factory=list)  # short tool-call log (audit)
    source: str = "llm"  # "llm" | "deterministic"
    seed_pattern_ids: list[str] = Field(default_factory=list)


class SynthesisRead(BaseModel):
    """The cross-timeframe fusion — the big-picture call over all the per-TF theses."""

    overall_bias: Bias = Bias.NEUTRAL
    headline: str = ""
    primary_timeframe: Timeframe | None = None
    nested_context: str = ""  # continuation / nesting across D/W/M
    long_term_forming: str = ""  # the long-horizon base + its breakout entry


class TickerAnalysis(BaseModel):
    schema_version: int = 3
    symbol: str
    generated_at: datetime
    timeframes: list[Timeframe] = Field(default_factory=list)
    summary: AnalysisSummary
    patterns: list[DetectedPattern] = Field(default_factory=list)
    charts: list[ChartArtifact] = Field(default_factory=list)
    notes: list[AnalyticalNote] = Field(default_factory=list)
    indicators: list[IndicatorSnapshot] = Field(default_factory=list)
    # AI analyst output (v3). Empty on the deterministic-only / legacy path.
    theses: list[TimeframeThesis] = Field(default_factory=list)
    synthesis: SynthesisRead | None = None

    def patterns_for(self, tf: Timeframe) -> list[DetectedPattern]:
        return [p for p in self.patterns if p.timeframe == tf]

    def thesis_for(self, tf: Timeframe) -> TimeframeThesis | None:
        return next((t for t in self.theses if t.timeframe == tf), None)

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


# --- Market Regime (classical market-conditions dashboard) ---


class RegimeState(StrEnum):
    """Overall market state — the IBD/Weinstein-style ladder for a LONG book."""

    CONFIRMED_UPTREND = "confirmed_uptrend"
    UPTREND_UNDER_PRESSURE = "uptrend_under_pressure"
    NEUTRAL = "neutral"  # choppy / no clear primary trend
    CORRECTION = "correction"
    BEAR = "bear"  # primary downtrend / Stage 4


class LongPosture(StrEnum):
    """What the regime implies for new long swing exposure."""

    AGGRESSIVE = "aggressive"  # buy breakouts, full exposure
    SELECTIVE = "selective"  # only A+ setups, reduce size
    DEFENSIVE = "defensive"  # raise cash, no new buys
    CASH = "cash"  # stand aside


class RegimeMetric(BaseModel):
    """One book-grounded reading (e.g. distribution-day count, Power Trend on/off)."""

    key: str
    label: str
    value: str  # formatted for display, e.g. "4 in 25d", "above (rising)", "$72.40"
    status: Bias = Bias.NEUTRAL
    detail: str = ""  # one-line interpretation
    source_tag: str = ""  # the authority/book, e.g. "Dow Theory", "O'Neil"
    numeric: float | None = None  # optional raw value (for sorting/thresholds)


class RegimePillar(BaseModel):
    """A cluster of related metrics with an aggregate status (one of the 5 pillars)."""

    key: str
    name: str
    status: Bias = Bias.NEUTRAL
    score: float = 0.0  # -1 (bearish) .. +1 (bullish)
    summary: str = ""
    metrics: list[RegimeMetric] = Field(default_factory=list)


class ChartMarker(BaseModel):
    ts: datetime
    label: str = ""
    color: str = ""
    position: str = "belowBar"  # lightweight-charts: aboveBar|belowBar|inBar
    shape: str = "circle"  # circle|arrowUp|arrowDown|square


class RegimePoint(BaseModel):
    ts: datetime
    value: float


class RegimeCandle(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float


class RegimeSeries(BaseModel):
    label: str
    kind: str = "line"  # "line" -> points; "candle" -> candles
    color: str = ""
    points: list[RegimePoint] = Field(default_factory=list)
    candles: list[RegimeCandle] = Field(default_factory=list)


class RegimeChart(BaseModel):
    """The actual time-series behind a consideration, so the dashboard can draw it."""

    key: str
    title: str
    pillar_key: str = ""
    series: list[RegimeSeries] = Field(default_factory=list)
    markers: list[ChartMarker] = Field(default_factory=list)
    note: str = ""


class RegimeSnapshot(BaseModel):
    """The full market-conditions read: the input data (charts + metrics) AND the
    conclusion (mood/state/posture/narrative). Persisted whole so the dashboard
    redraws entirely from the DB with no re-fetch."""

    schema_version: int = 1
    generated_at: datetime
    overall_state: RegimeState = RegimeState.NEUTRAL
    long_posture: LongPosture = LongPosture.SELECTIVE
    mood: str = ""  # short human label, e.g. "Risk-on, broad uptrend"
    score: float = 0.0  # -1 (bearish) .. +1 (bullish)
    headline: str = ""
    narrative: str = ""
    source: str = "deterministic"  # "llm" | "deterministic"
    pillars: list[RegimePillar] = Field(default_factory=list)
    charts: list[RegimeChart] = Field(default_factory=list)

    def pillar(self, key: str) -> RegimePillar | None:
        return next((p for p in self.pillars if p.key == key), None)

    def charts_for(self, pillar_key: str) -> list[RegimeChart]:
        return [c for c in self.charts if c.pillar_key == pillar_key]
