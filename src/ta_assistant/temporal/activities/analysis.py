"""Activities for the ticker-analysis pipeline. All I/O + heavy libs live here;
each returns/accepts the TickerAnalysis pydantic model (round-trips via the
pydantic data converter). Blocking work is offloaded with asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime
from pathlib import Path

import pandas as pd
from temporalio import activity

from ta_assistant.analyst.cache import bars_hash, cache_get, cache_put, content_hash
from ta_assistant.analyst.prompts import PROMPT_VERSION
from ta_assistant.analyst.provider import deterministic_thesis, get_analyst, textbookize
from ta_assistant.analyst.tools import ToolContext
from ta_assistant.config import Settings, get_settings
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
from ta_assistant.patterns.levels import cluster_prices
from ta_assistant.patterns.trendlines import fit_trendline
from ta_assistant.presentation.charts import render_mpl, render_thesis_png
from ta_assistant.synthesis.notes import analyze_notes, snapshot
from ta_assistant.synthesis.schema import (
    AnalysisSummary,
    AnalyticalNote,
    Bias,
    ChartArtifact,
    DetectedPattern,
    Shape,
    ShapeKind,
    ShapePoint,
    SynthesisRead,
    TickerAnalysis,
    Timeframe,
    TimeframeThesis,
)

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


def _seed_fingerprint(seeds: list[DetectedPattern]) -> str:
    """Compact signature of the seed candidates, so a change in the deterministic hints
    invalidates the cached thesis."""
    return "|".join(
        sorted(f"{p.pattern_type}:{p.direction}:{round(p.entry or 0, 2)}" for p in seeds)
    )


def _seed_line(p: DetectedPattern) -> str:
    bits = []
    if p.entry is not None:
        bits.append(f"breakout {p.entry:.2f}")
    if p.target is not None:
        bits.append(f"target {p.target:.2f}")
    if p.stop is not None:
        bits.append(f"stop {p.stop:.2f}")
    lv = (" (" + ", ".join(bits) + ")") if bits else ""
    return f"{p.pattern_type} [{p.tier}, {p.direction}, {p.status.value}]{lv}"


def _digest(symbol: str, tf: Timeframe, bars: pd.DataFrame, seeds: list[DetectedPattern]) -> str:
    last = float(bars["close"].to_numpy(dtype=float)[-1]) if len(bars) else 0.0
    hints = "; ".join(_seed_line(p) for p in seeds) or "none"
    return (
        f"Ticker {symbol}, {tf.value} timeframe. The image is the recent {tf.value} candles "
        f"with MA50/150/200 and a volume pane; last close {last:.2f}.\n"
        f"Engine candidate structures [tier, direction, status] — CORE = tradeable, "
        f"SUPPORT = context only (rounding/double/triple bottom): {hints}.\n"
        f"Pick a CORE structure as the trade (its name is pattern_label); put any SUPPORT "
        f"structures into supporting_factors (they strengthen the setup, they are not the "
        f"trade). Measure with the tools and call submit_thesis with exact levels, the "
        f"shapes to draw, and price notes."
    )


def _provider_model(settings: Settings) -> tuple[str, str]:
    provider = settings.active_provider
    model = settings.anthropic_model if provider == "anthropic" else settings.openai_model
    return provider, model


def _rail(window: pd.DataFrame, x0: int, x1: int, p0: float, p1: float, role: str) -> Shape:
    return Shape(
        kind=ShapeKind.TRENDLINE,
        points=[
            ShapePoint(ts=window.index[x0].to_pydatetime(), price=p0),
            ShapePoint(ts=window.index[x1].to_pydatetime(), price=p1),
        ],
        role=role,
        label=role,
    )


def _sloped_rail(window: pd.DataFrame, pivs: list, x1: int, role: str) -> Shape:  # type: ignore[type-arg]
    """Theil-Sen line through ALL the given pivots in LOG space (so it spans the whole
    structure, not just the last few), projected to bar x1 to land on a log-scaled chart."""
    line = fit_trendline([p.idx for p in pivs], [math.log(p.price) for p in pivs])
    x0 = pivs[0].idx
    return _rail(window, x0, x1, math.exp(line.value_at(x0)), math.exp(line.value_at(x1)), role)


def _log_rails(window: pd.DataFrame, tf_value: str) -> list[Shape]:
    """The two clean trendlines a chartist draws to bound a structure. Support follows the
    recent swing LOWS (rising in an uptrend). Resistance is a FLAT level when the highs
    repeatedly hit one (ascending-triangle look), else a sloped line through the highs."""
    if len(window) < _MIN_BARS:
        return []
    ctx = build_context(window, tf_value, atr_mult=2.0, min_pct=0.02)
    last = len(window) - 1
    highs = [p for p in ctx.pivots if p.kind == "H" and not p.provisional]
    lows = [p for p in ctx.pivots if p.kind == "L" and not p.provisional]
    out: list[Shape] = []
    if len(lows) >= 2:
        out.append(_sloped_rail(window, lows, last, "support"))
    if len(highs) >= 2:
        tol = max(0.04 * ctx.last_close, 1.5 * ctx.atr_at(last))
        level, touches = cluster_prices([p.price for p in highs], tol)[0]  # strongest level
        members = [p for p in highs if abs(p.price - level) <= tol]
        if touches >= 2 and len(members) >= 2:  # flat resistance the highs keep hitting
            out.append(_rail(window, members[0].idx, last, level, level, "resistance"))
        else:
            out.append(_sloped_rail(window, highs, last, "resistance"))
    return out


def _apply_frame_rails(
    thesis: TimeframeThesis, bars: pd.DataFrame, lookback: int, tf: Timeframe
) -> TimeframeThesis:
    """Guarantee clean bounding lines on EVERY thesis: H&S keeps its neckline+arc; anything
    else gets the two log-fitted rails spanning the structure (so no timeframe is line-less,
    and short detector rails are replaced by ones that span the whole base)."""
    if any(s.role == "neckline" for s in thesis.shapes):
        return thesis  # head-and-shoulders: the neckline + arc are the geometry
    window = bars.iloc[-lookback:] if len(bars) > lookback else bars
    frame = _log_rails(window, tf.value)
    if not frame:
        return thesis
    kept = [
        s
        for s in thesis.shapes
        if not (s.kind == ShapeKind.TRENDLINE and s.role in ("resistance", "support"))
    ]
    thesis.shapes = frame + kept
    return thesis


def _analyze_one(analysis: TickerAnalysis, tf: Timeframe, workflow_id: str) -> TimeframeThesis:
    """Run the AI chartist's bounded vision+tool loop for ONE timeframe (cached; falls back
    to the deterministic engine thesis on no-key / failure / insane levels)."""
    settings = get_settings()
    bars = load_bars(analysis.symbol, _TF_CODE[tf])
    seeds_all = analysis.patterns_for(tf)
    if len(bars) == 0:
        return deterministic_thesis(tf, seeds_all)
    seeds = _cluster_reps(seeds_all)  # deduped hints for the analyst
    recent = bars.iloc[-_VISION_BARS[tf] :] if len(bars) > _VISION_BARS[tf] else bars
    vision_png = _charts_dir(analysis.symbol, workflow_id) / f"_vision_{tf.value}.png"
    render_mpl(recent, [], str(vision_png), title=f"{analysis.symbol} — {tf.value}")

    provider, model = _provider_model(settings)
    key = content_hash(
        {
            "kind": "thesis",
            "symbol": analysis.symbol,
            "tf": tf.value,
            "prompt": PROMPT_VERSION,
            "provider": provider,
            "model": model,
            "bars": bars_hash(bars),
            "seed": _seed_fingerprint(seeds),
        }
    )
    def _frame(t: TimeframeThesis) -> TimeframeThesis:
        return _apply_frame_rails(t, bars, _OVERVIEW_BARS[tf], tf)

    cached = cache_get(key, TimeframeThesis)
    if cached is not None:
        return _frame(cached)

    ctx = ToolContext(symbol=analysis.symbol, timeframe=tf.value, df=bars, seeds=seeds)
    result = get_analyst(settings).run_thesis_loop(
        user_text=_digest(analysis.symbol, tf, bars, seeds),
        image_paths=[str(vision_png)],
        tool_ctx=ctx,
        timeframe=tf,
    )
    if result.thesis is not None and result.thesis.source == "llm":
        # snap the drawing + levels to the matching detector's textbook geometry (clean
        # rails, correct LS/Head/RS order, deduped price tags); keep the analyst's read.
        thesis = textbookize(result.thesis, seeds_all)
        cache_put(key, model, thesis)
        return _frame(thesis)
    # fallback: deterministic engine read (LLM disabled, failed, or produced no valid thesis)
    return _frame(deterministic_thesis(tf, seeds_all))


_TF_WEIGHT = {Timeframe.WEEKLY: 3, Timeframe.DAILY: 2, Timeframe.MONTHLY: 1}


def _build_synthesis(symbol: str, theses: list[TimeframeThesis]) -> SynthesisRead:
    """Fuse the per-timeframe theses into one big-picture read (deterministic over the AI
    theses): prefer the swing-trader's weekly/daily structure, bias from its confidence."""
    if not theses:
        return SynthesisRead(overall_bias=Bias.NEUTRAL, headline=f"{symbol}: no analysis")
    pool = [t for t in theses if t.direction == "bullish" and t.confidence > 0] or theses
    primary = max(pool, key=lambda t: (_TF_WEIGHT.get(t.timeframe, 0), round(t.confidence, 2)))
    bullish = primary.direction == "bullish" and primary.confidence >= 0.55
    tgt = f" → target {primary.target:.2f}" if primary.target is not None else ""
    headline = (
        f"{symbol}: {primary.pattern_label} ({primary.status.value}) "
        f"on {primary.timeframe.value}{tgt}"
    )
    nested = "; ".join(
        f"{t.timeframe.value}: {t.pattern_label}" for t in theses if t is not primary
    )
    big_tfs = (Timeframe.MONTHLY, Timeframe.WEEKLY)
    lt = next(
        (t for t in theses if t.timeframe in big_tfs and t is not primary),
        None,
    )
    return SynthesisRead(
        overall_bias=Bias.BULLISH if bullish else Bias.NEUTRAL,
        headline=headline,
        primary_timeframe=primary.timeframe,
        nested_context=nested,
        long_term_forming=(f"{lt.timeframe.value} {lt.pattern_label}" if lt else ""),
    )


def _synthesize(analysis: TickerAnalysis, theses: list[TimeframeThesis]) -> TickerAnalysis:
    read = _build_synthesis(analysis.symbol, theses)
    out = analysis.model_copy(update={"theses": theses, "synthesis": read})
    primary = next((t for t in theses if t.timeframe == read.primary_timeframe), None)
    flags = [n.message for n in out.notes if n.severity.value in ("warning", "caution")][:3]
    parts = [read.headline.rstrip(".") + "."]
    if primary is not None and primary.rationale:
        parts.append(primary.rationale.strip())
    if flags:
        parts.append("Watch: " + " ".join(flags))
    out.summary.overall_bias = read.overall_bias
    out.summary.headline = read.headline
    out.summary.narrative = " ".join(parts)
    return out


def _render(analysis: TickerAnalysis, workflow_id: str) -> TickerAnalysis:
    """Render one static chart per timeframe from the AI analyst's thesis (its shapes +
    price notes), drawn on a recent window."""
    charts_dir = _charts_dir(analysis.symbol, workflow_id)
    charts: list[ChartArtifact] = []
    for tf in analysis.timeframes:
        bars = load_bars(analysis.symbol, _TF_CODE[tf])
        if len(bars) == 0:
            continue
        thesis = analysis.thesis_for(tf)
        out = charts_dir / f"{tf.value}.png"
        if thesis is not None:
            render_thesis_png(
                bars,
                thesis,
                str(out),
                title=f"{analysis.symbol} — {tf.value}: {thesis.pattern_label}",
                max_bars=_OVERVIEW_BARS[tf],
            )
        else:
            render_mpl(
                bars, [], str(out), title=f"{analysis.symbol} — {tf.value}",
                max_bars=_OVERVIEW_BARS[tf],
            )
        charts.append(ChartArtifact(timeframe=tf, png_path=str(out)))
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
async def analyze_timeframe(
    analysis: TickerAnalysis, timeframe: Timeframe, workflow_id: str
) -> TimeframeThesis:
    """Run the AI chartist's bounded vision+tool loop for ONE timeframe (cached;
    deterministic fallback on no-key / failure). Returns that timeframe's thesis."""
    return await asyncio.to_thread(_analyze_one, analysis, timeframe, workflow_id)


@activity.defn
async def synthesize(
    analysis: TickerAnalysis, theses: list[TimeframeThesis]
) -> TickerAnalysis:
    """Fuse the per-timeframe theses into the overall bias/headline/narrative."""
    return await asyncio.to_thread(_synthesize, analysis, theses)


@activity.defn
async def render_charts(analysis: TickerAnalysis, workflow_id: str) -> TickerAnalysis:
    """Render one static chart per timeframe from the final thesis shapes."""
    return await asyncio.to_thread(_render, analysis, workflow_id)


@activity.defn
async def persist_analysis_result(analysis: TickerAnalysis, workflow_id: str) -> str:
    """Idempotently store the TickerAnalysis JSON keyed by workflow_id."""
    return await asyncio.to_thread(_persist, analysis, workflow_id)
