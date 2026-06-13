"""Activities for the ticker-analysis pipeline. All I/O + heavy libs live here;
each returns/accepts the TickerAnalysis pydantic model (round-trips via the
pydantic data converter). Blocking work is offloaded with asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pandas as pd
from temporalio import activity

from ta_assistant.config import get_settings
from ta_assistant.data.bars_repo import load_bars, upsert_bars
from ta_assistant.data.earnings import fetch_earnings_info
from ta_assistant.data.providers import get_daily_history
from ta_assistant.data.resample import to_monthly, to_weekly
from ta_assistant.db.models import Analysis
from ta_assistant.db.session import session_scope
from ta_assistant.patterns.assemble import assign_conflicts, assign_nesting, to_detected_pattern
from ta_assistant.patterns.consensus import assign_consensus, pick_headline
from ta_assistant.patterns.context import build_context
from ta_assistant.patterns.detectors import detect_all
from ta_assistant.patterns.detectors.base import is_actionable, sane_levels
from ta_assistant.presentation.charts import render_mpl, render_pattern_png
from ta_assistant.synthesis.notes import analyze_notes, snapshot
from ta_assistant.synthesis.schema import (
    AnalysisSummary,
    AnalyticalNote,
    Bias,
    ChartArtifact,
    DetectedPattern,
    TickerAnalysis,
    Timeframe,
)
from ta_assistant.synthesis.validator import apply_consensus, consensus_cached, get_validator

_MIN_BARS = 20
_TF_CODE = {Timeframe.DAILY: "D", Timeframe.WEEKLY: "W", Timeframe.MONTHLY: "M"}
# Detection horizon per timeframe: daily ~2y (recent), weekly ~5y, monthly ~20y.
# This keeps patterns relevant (not 1990s structure) and bounds neckline extrapolation.
_WINDOW = {Timeframe.DAILY: 504, Timeframe.WEEKLY: 260, Timeframe.MONTHLY: 240}
# A pattern is actionable only if its right edge is recent (else it already played out
# years ago). Multi-year bases that are resolving NOW still pass (their region ends now).
_RECENT = {Timeframe.DAILY: 80, Timeframe.WEEKLY: 30, Timeframe.MONTHLY: 18}
# Second, ZOOMED-IN detection pass: a finer ATR-ZigZag over a recent sub-window so the
# CURRENT tradeable structure is seen (the coarse full-window pass only resolves the
# multi-year base). Dedup/consensus then collapses the overlap with the base pass.
# Tuned so the weekly (the swing trader's canvas) resolves the live consolidation.
_RECENT_WINDOW = {Timeframe.DAILY: 160, Timeframe.WEEKLY: 64, Timeframe.MONTHLY: 48}
_RECENT_MULT = {Timeframe.DAILY: 2.0, Timeframe.WEEKLY: 1.6, Timeframe.MONTHLY: 1.8}
_RECENT_MIN_PCT = {Timeframe.DAILY: 0.02, Timeframe.WEEKLY: 0.018, Timeframe.MONTHLY: 0.02}


def _detect_pass(
    tf: Timeframe,
    frame: pd.DataFrame,
    patterns: list[DetectedPattern],
    counter: int,
    *,
    atr_mult: float,
    min_pct: float,
) -> int:
    """Run all detectors over one (frame, pivot-scale) and append the sane, actionable
    candidates. Indices are stored against `frame.index`; the renderer positions by
    timestamp, so passes over different windows compose cleanly."""
    if len(frame) < _MIN_BARS:
        return counter
    ctx = build_context(frame, tf.value, atr_mult=atr_mult, min_pct=min_pct)
    recent_cutoff = len(frame) - _RECENT[tf]
    last_close = ctx.last_close
    for cand in detect_all(ctx):
        if not sane_levels(cand, last_close):
            continue  # no degenerate/absurd levels reach the schema
        if not is_actionable(cand, last_close, recent_cutoff):
            continue  # only currently-tradeable patterns
        patterns.append(to_detected_pattern(cand, f"{tf.value[0]}{counter}", frame.index))
        counter += 1
    return counter


def _summary(symbol: str, patterns: list[DetectedPattern], price_now: float) -> AnalysisSummary:
    best = pick_headline(patterns)
    if best is None:
        return AnalysisSummary(
            overall_bias=Bias.NEUTRAL,
            headline=f"{symbol}: no clean long setup detected",
            price_now=price_now,
        )
    if best.conflicts_with:  # a bearish structure caps the upside
        return AnalysisSummary(
            overall_bias=Bias.NEUTRAL,
            headline=f"{symbol}: {best.display_label} long, but {best.caution or 'upside capped'}",
            price_now=price_now,
            best_setup_id=best.id,
        )
    return AnalysisSummary(
        overall_bias=Bias.BULLISH,
        headline=f"{symbol}: {best.display_label} ({best.status.value}) on {best.timeframe.value}",
        price_now=price_now,
        best_setup_id=best.id,
    )


def _narrative(
    summary: AnalysisSummary, notes: list[AnalyticalNote], best: DetectedPattern | None
) -> str:
    parts = [summary.headline.rstrip(".") + "."]
    if best is not None and best.caution:
        parts.append(best.caution[0].upper() + best.caution[1:] + ".")
    flags = [n.message for n in notes if n.severity.value in ("warning", "caution")][:3]
    if flags:
        parts.append("Watch: " + " ".join(flags))
    return " ".join(parts)


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
        timeframes.append(tf)
        # Pass 1: coarse pivots over the full horizon (multi-year bases).
        base = bars.iloc[-_WINDOW[tf] :] if len(bars) > _WINDOW[tf] else bars
        counter = _detect_pass(tf, base, patterns, counter, atr_mult=3.0, min_pct=0.03)
        # Pass 2: finer pivots over a recent sub-window (the current tradeable structure).
        rw = _RECENT_WINDOW[tf]
        if len(bars) > rw + 5:
            recent = bars.iloc[-rw:]
            counter = _detect_pass(
                tf,
                recent,
                patterns,
                counter,
                atr_mult=_RECENT_MULT[tf],
                min_pct=_RECENT_MIN_PCT[tf],
            )

    assign_nesting(patterns)
    assign_conflicts(patterns)
    assign_consensus(patterns)  # dedup competing labels -> primary/secondary/cap roles
    price_now = float(daily["close"].to_numpy(dtype=float)[-1])
    summary = _summary(symbol, patterns, price_now)

    frames = {Timeframe.DAILY: daily, Timeframe.WEEKLY: weekly, Timeframe.MONTHLY: monthly}
    snaps = {tf: snapshot(frames[tf], tf) for tf in timeframes if len(frames[tf]) >= _MIN_BARS}
    earnings = fetch_earnings_info(symbol, now.date())
    notes = analyze_notes(daily, snaps, patterns, earnings.days_until if earnings else None)
    summary.narrative = _narrative(summary, notes, pick_headline(patterns))

    return TickerAnalysis(
        symbol=symbol,
        generated_at=now,
        timeframes=timeframes,
        summary=summary,
        patterns=patterns,
        notes=notes,
        indicators=list(snaps.values()),
    )


# Recent-window sizes for the chart the analyst (and user) actually look at — the live
# structure, not 20 years of history.
_VISION_BARS = {Timeframe.DAILY: 180, Timeframe.WEEKLY: 90, Timeframe.MONTHLY: 72}
# The per-timeframe overview keeps a bit more context than the vision image, but still
# stays zoomed to the recent action (not the full multi-decade history).
_OVERVIEW_BARS = {Timeframe.DAILY: 200, Timeframe.WEEKLY: 130, Timeframe.MONTHLY: 90}


def _charts_dir(symbol: str, workflow_id: str) -> Path:
    out = Path(get_settings().db_path).resolve().parent / "charts" / symbol / workflow_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def _cluster_reps(patterns: list[DetectedPattern], limit: int = 6) -> list[DetectedPattern]:
    """One representative per structure cluster (the distinct candidates for the analyst to
    arbitrate). Always include the deterministically-surfaced ones; fill with the strongest
    of the rest up to `limit`."""
    best: dict[int, DetectedPattern] = {}
    for i, p in enumerate(patterns):
        cid = p.cluster_id if p.cluster_id is not None else -1 - i
        cur = best.get(cid)
        if cur is None or p.confidence > cur.confidence:
            best[cid] = p
    reps = list(best.values())
    surfaced = [p for p in reps if p.role in ("primary", "secondary", "cap")]
    others = sorted(
        (p for p in reps if p.role == "considered"), key=lambda p: p.confidence, reverse=True
    )
    return (surfaced + others)[: max(limit, len(surfaced))]


def _finalize_summary(analysis: TickerAnalysis, reads: dict[Timeframe, str]) -> None:
    """Recompute the headline/bias/narrative from the FINAL consensus roles + vision read."""
    head = pick_headline(analysis.patterns)
    s = analysis.summary
    if head is None:
        s.overall_bias = Bias.NEUTRAL
        s.headline = f"{analysis.symbol}: no clean long setup detected"
        s.best_setup_id = None
    else:
        s.best_setup_id = head.id
        # NEUTRAL only when geometry sees an interlock AND consensus actually surfaced a cap
        # on that timeframe (so the analyst can overrule a spurious geometric conflict).
        capped = bool(head.conflicts_with) and any(
            p.role == "cap" for p in analysis.patterns_for(head.timeframe)
        )
        if capped:
            s.overall_bias = Bias.NEUTRAL
            s.headline = (
                f"{analysis.symbol}: {head.display_label} long, "
                f"but {head.caution or 'upside capped'}"
            )
        else:
            s.overall_bias = Bias.BULLISH
            s.headline = (
                f"{analysis.symbol}: {head.display_label} "
                f"({head.status.value}) on {head.timeframe.value}"
            )
    vision_read = reads.get(head.timeframe) if head else None
    flags = [n.message for n in analysis.notes if n.severity.value in ("warning", "caution")][:3]
    parts = [vision_read.strip()] if vision_read else [s.headline.rstrip(".") + "."]
    if head is not None and head.caution and not vision_read:
        parts.append(head.caution[0].upper() + head.caution[1:] + ".")
    if flags:
        parts.append("Watch: " + " ".join(flags))
    s.narrative = " ".join(parts)


def _validate(analysis: TickerAnalysis, workflow_id: str) -> TickerAnalysis:
    """Vision CONSENSUS per timeframe: render a clean recent-window chart, ask the analyst
    to pick the dominant structure(s) among the deduped candidates + relabel, then recompute
    the summary. No-op-safe (NullConsensus keeps the deterministic roles) with no key."""
    settings = get_settings()
    validator = get_validator(settings)
    charts_dir = _charts_dir(analysis.symbol, workflow_id)
    reads: dict[Timeframe, str] = {}
    for tf in analysis.timeframes:
        tf_patterns = analysis.patterns_for(tf)
        if not tf_patterns:
            continue
        bars = load_bars(analysis.symbol, _TF_CODE[tf])
        if len(bars) == 0:
            continue
        recent = bars.iloc[-_VISION_BARS[tf] :] if len(bars) > _VISION_BARS[tf] else bars
        vision_png = charts_dir / f"_vision_{tf.value}.png"
        render_mpl(recent, [], str(vision_png), title=f"{analysis.symbol} — {tf.value}")
        reps = _cluster_reps(tf_patterns)
        result = consensus_cached(validator, tf.value, str(vision_png), reps, settings.openai_model)
        apply_consensus(tf_patterns, result)
        # long-side backstop: if consensus surfaced no primary but a valid bullish structure
        # exists, surface the strongest one (a bearish 'cap' still flags the interlock risk).
        if not any(p.role == "primary" for p in reps):
            bulls = [p for p in reps if p.direction == "bullish" and p.llm_is_valid is not False]
            if bulls:
                max(bulls, key=lambda p: p.confidence).role = "primary"
        if result.read:
            reads[tf] = result.read
    _finalize_summary(analysis, reads)
    return analysis


def _render(analysis: TickerAnalysis, workflow_id: str) -> TickerAnalysis:
    """Render the display charts AFTER consensus, so they show only the final surfaced
    structures: one annotated per-timeframe overview + a focused PNG per surfaced pattern."""
    charts_dir = _charts_dir(analysis.symbol, workflow_id)
    charts: list[ChartArtifact] = []
    for tf in analysis.timeframes:
        bars = load_bars(analysis.symbol, _TF_CODE[tf])
        if len(bars) == 0:
            continue
        surfaced = analysis.surfaced_for(tf)
        out = charts_dir / f"{tf.value}.png"
        render_mpl(
            bars, surfaced, str(out), title=f"{analysis.symbol} — {tf.value}",
            max_bars=_OVERVIEW_BARS[tf],
        )
        charts.append(
            ChartArtifact(timeframe=tf, png_path=str(out), pattern_ids=[p.id for p in surfaced])
        )
        for p in surfaced:
            ppath = charts_dir / f"pattern_{p.id}.png"
            render_pattern_png(bars, p, str(ppath), title=f"{analysis.symbol} — {p.display_label}")
            p.chart_png = str(ppath)
    return analysis.model_copy(update={"charts": charts})


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
async def validate_patterns(analysis: TickerAnalysis, workflow_id: str) -> TickerAnalysis:
    """Vision consensus per timeframe: pick the dominant structure(s), relabel, score, and
    recompute the summary (cached; deterministic no-op if the LLM is disabled)."""
    return await asyncio.to_thread(_validate, analysis, workflow_id)


@activity.defn
async def render_charts(analysis: TickerAnalysis, workflow_id: str) -> TickerAnalysis:
    """Render the final display charts (per-timeframe overview + per-pattern PNGs)."""
    return await asyncio.to_thread(_render, analysis, workflow_id)


@activity.defn
async def persist_analysis_result(analysis: TickerAnalysis, workflow_id: str) -> str:
    """Idempotently store the TickerAnalysis JSON keyed by workflow_id."""
    return await asyncio.to_thread(_persist, analysis, workflow_id)
