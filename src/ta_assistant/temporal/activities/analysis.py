"""Activities for the ticker-analysis pipeline. All I/O + heavy libs live here;
each returns/accepts the TickerAnalysis pydantic model (round-trips via the
pydantic data converter). Blocking work is offloaded with asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from temporalio import activity

from ta_assistant.config import get_settings
from ta_assistant.data.bars_repo import load_bars, upsert_bars
from ta_assistant.data.providers import get_daily_history
from ta_assistant.data.resample import to_monthly, to_weekly
from ta_assistant.db.models import Analysis
from ta_assistant.db.session import session_scope
from ta_assistant.patterns.assemble import assign_nesting, to_detected_pattern
from ta_assistant.patterns.context import build_context
from ta_assistant.patterns.detectors import detect_all
from ta_assistant.presentation.charts import render_mpl
from ta_assistant.synthesis.schema import (
    AnalysisSummary,
    Bias,
    ChartArtifact,
    DetectedPattern,
    TickerAnalysis,
    Timeframe,
)
from ta_assistant.synthesis.validator import apply_validation, get_validator, validate_cached

_MIN_BARS = 20
_TF_CODE = {Timeframe.DAILY: "D", Timeframe.WEEKLY: "W", Timeframe.MONTHLY: "M"}
_STATUS_RANK = {"triggered": 3, "confirmed": 2, "forming": 1, "invalidated": 0}
# Detection horizon per timeframe: daily ~2y (recent), weekly ~5y, monthly ~20y.
# This keeps patterns relevant (not 1990s structure) and bounds neckline extrapolation.
_WINDOW = {Timeframe.DAILY: 504, Timeframe.WEEKLY: 260, Timeframe.MONTHLY: 240}
# A pattern is actionable only if its right edge is recent (else it already played out
# years ago). Multi-year bases that are resolving NOW still pass (their region ends now).
_RECENT = {Timeframe.DAILY: 80, Timeframe.WEEKLY: 30, Timeframe.MONTHLY: 18}


def _best(patterns: list[DetectedPattern]) -> DetectedPattern | None:
    if not patterns:
        return None
    return max(patterns, key=lambda p: (_STATUS_RANK.get(p.status.value, 0), p.confidence))


def _summary(symbol: str, patterns: list[DetectedPattern], price_now: float) -> AnalysisSummary:
    best = _best(patterns)
    if best is None:
        return AnalysisSummary(
            overall_bias=Bias.NEUTRAL,
            headline=f"{symbol}: no clean long setup detected",
            price_now=price_now,
        )
    return AnalysisSummary(
        overall_bias=Bias.BULLISH,
        headline=f"{symbol}: {best.pattern_type} ({best.status.value}) on {best.timeframe.value}",
        price_now=price_now,
        best_setup_id=best.id,
    )


def _build(symbol: str, now_iso: str) -> TickerAnalysis:
    now = datetime.fromisoformat(now_iso).replace(tzinfo=None)
    daily, source = get_daily_history(symbol)
    if len(daily) == 0:
        return TickerAnalysis(
            symbol=symbol,
            generated_at=now,
            summary=AnalysisSummary(
                overall_bias=Bias.NEUTRAL, headline=f"{symbol}: no data", price_now=0.0
            ),
        )

    weekly = to_weekly(daily, now)
    monthly = to_monthly(daily, now)
    upsert_bars(daily, symbol, "D", source)
    upsert_bars(weekly, symbol, "W", source)
    upsert_bars(monthly, symbol, "M", source)

    patterns: list[DetectedPattern] = []
    timeframes: list[Timeframe] = []
    counter = 0
    for tf, bars in (
        (Timeframe.DAILY, daily),
        (Timeframe.WEEKLY, weekly),
        (Timeframe.MONTHLY, monthly),
    ):
        if len(bars) < _MIN_BARS:
            continue
        windowed = bars.iloc[-_WINDOW[tf] :] if len(bars) > _WINDOW[tf] else bars
        timeframes.append(tf)
        ctx = build_context(windowed, tf.value)
        recent_cutoff = len(windowed) - _RECENT[tf]
        for cand in detect_all(ctx):
            if cand.levels.get("breakout", 0.0) <= 0 or cand.levels.get("target", 0.0) <= 0:
                continue  # drop degenerate levels defensively
            if cand.region_end_idx < recent_cutoff:
                continue  # pattern completed too long ago to be actionable
            patterns.append(to_detected_pattern(cand, f"{tf.value[0]}{counter}", windowed.index))
            counter += 1

    assign_nesting(patterns)
    price_now = float(daily["close"].to_numpy(dtype=float)[-1])
    return TickerAnalysis(
        symbol=symbol,
        generated_at=now,
        timeframes=timeframes,
        summary=_summary(symbol, patterns, price_now),
        patterns=patterns,
    )


def _render(analysis: TickerAnalysis, workflow_id: str) -> TickerAnalysis:
    charts_dir = (
        Path(get_settings().db_path).resolve().parent / "charts" / analysis.symbol / workflow_id
    )
    charts_dir.mkdir(parents=True, exist_ok=True)
    charts: list[ChartArtifact] = []
    for tf in analysis.timeframes:
        bars = load_bars(analysis.symbol, _TF_CODE[tf])
        if len(bars) == 0:
            continue
        pats = analysis.patterns_for(tf)
        out = charts_dir / f"{tf.value}.png"
        render_mpl(bars, pats, str(out), title=f"{analysis.symbol} — {tf.value}")
        charts.append(
            ChartArtifact(timeframe=tf, png_path=str(out), pattern_ids=[p.id for p in pats])
        )
    return analysis.model_copy(update={"charts": charts})


def _validate(analysis: TickerAnalysis) -> TickerAnalysis:
    settings = get_settings()
    validator = get_validator(settings)
    chart_by_tf = {c.timeframe: c.png_path for c in analysis.charts}
    for pattern in analysis.patterns:
        png = chart_by_tf.get(pattern.timeframe)
        result = validate_cached(validator, pattern, png, settings.openai_model)
        apply_validation(pattern, result)
    return analysis


def _persist(analysis: TickerAnalysis, workflow_id: str) -> str:
    dedup_key = f"{workflow_id}:{analysis.symbol}"
    payload = analysis.model_dump_json()
    with session_scope() as session:
        existing = session.get(Analysis, dedup_key)
        if existing is None:
            session.add(Analysis(dedup_key=dedup_key, symbol=analysis.symbol, payload_json=payload))
        else:
            existing.payload_json = payload
    return dedup_key


@activity.defn
async def build_analysis(symbol: str, now_iso: str) -> TickerAnalysis:
    """Fetch all-time history, cache bars (D/W/M), detect patterns, build summary."""
    return await asyncio.to_thread(_build, symbol.upper(), now_iso)


@activity.defn
async def render_charts(analysis: TickerAnalysis, workflow_id: str) -> TickerAnalysis:
    """Render an annotated PNG per timeframe; attach chart paths."""
    return await asyncio.to_thread(_render, analysis, workflow_id)


@activity.defn
async def validate_patterns(analysis: TickerAnalysis) -> TickerAnalysis:
    """OpenAI vision validation/narration over each pattern (cached; no-op if disabled)."""
    return await asyncio.to_thread(_validate, analysis)


@activity.defn
async def persist_analysis_result(analysis: TickerAnalysis, workflow_id: str) -> str:
    """Idempotently store the TickerAnalysis JSON keyed by workflow_id."""
    return await asyncio.to_thread(_persist, analysis, workflow_id)
