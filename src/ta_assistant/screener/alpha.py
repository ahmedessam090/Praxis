"""The alpha decision (agent2) + re-evaluation (agent3).

Pure decision logic (no DB): build a digest from the full TickerAnalysis + regime + sector,
ask the LLM to judge whether it's a genuine alpha opportunity, validate the JSON, and fall
back to a deterministic classical gate when there's no key / the output is unusable. Mirrors
regime/narrative.py. Caching + get_analyst live in the activity layer.
"""

from __future__ import annotations

import json
import logging

from ta_assistant.analyst.prompts import ALPHA_REFRESH_SYSTEM, ALPHA_SYSTEM
from ta_assistant.analyst.provider import LLMAnalyst
from ta_assistant.synthesis.schema import (
    AlphaReason,
    AlphaVerdict,
    Bias,
    IndicatorSnapshot,
    LongPosture,
    RegimeSnapshot,
    RegimeState,
    TickerAnalysis,
    Timeframe,
    TimeframeThesis,
)

logger = logging.getLogger(__name__)

_RISK_ON = {RegimeState.CONFIRMED_UPTREND, RegimeState.UPTREND_UNDER_PRESSURE}
_OK_POSTURE = {LongPosture.AGGRESSIVE, LongPosture.SELECTIVE}


# --------------------------------------------------------------------------- fact extraction


def _daily_ind(analysis: TickerAnalysis) -> IndicatorSnapshot | None:
    return next((i for i in analysis.indicators if i.timeframe == Timeframe.DAILY), None)


def _weekly_ind(analysis: TickerAnalysis) -> IndicatorSnapshot | None:
    return next((i for i in analysis.indicators if i.timeframe == Timeframe.WEEKLY), None)


def _best_thesis(analysis: TickerAnalysis) -> TimeframeThesis | None:
    bulls = [t for t in analysis.theses if t.direction == "bullish"]
    if not bulls:
        return None
    return max(
        bulls,
        key=lambda t: (
            t.entry is not None and t.target is not None and t.stop is not None,
            t.confidence,
        ),
    )


def _sector_status(regime: RegimeSnapshot | None, sector: str) -> Bias | None:
    if regime is None:
        return None
    pillar = regime.pillar("sector_leadership")
    if pillar is None:
        return None
    m = next((m for m in pillar.metrics if m.key == f"sector_{sector}"), None)
    return m.status if m else None


def _rr(entry: float | None, stop: float | None, target: float | None) -> float | None:
    if entry is None or stop is None or target is None or abs(entry - stop) < 1e-9:
        return None
    return round((target - entry) / (entry - stop), 2)


# --------------------------------------------------------------------------- digest


def build_alpha_digest(
    analysis: TickerAnalysis,
    regime: RegimeSnapshot | None,
    sector: str,
    sector_status: Bias | None,
) -> str:
    s = analysis.summary
    lines = [
        f"ALPHA EVALUATION — {analysis.symbol} (sector: {sector})",
        f"Bias: {s.overall_bias.value}; last price: {s.price_now:.2f}",
        f"Headline: {s.headline}",
    ]
    if s.narrative:
        lines.append(f"Narrative: {s.narrative}")
    if analysis.synthesis:
        syn = analysis.synthesis
        if syn.nested_context:
            lines.append(f"Across timeframes: {syn.nested_context}")
        if syn.long_term_forming:
            lines.append(f"Long-term: {syn.long_term_forming}")
    lines.append("")
    lines.append("## Per-timeframe theses")
    for t in analysis.theses:
        lines.append(
            f"- {t.timeframe.value}: {t.pattern_label} ({t.status.value}, {t.direction}, "
            f"conf {t.confidence:.2f}) entry={t.entry} breakout={t.breakout} "
            f"target={t.target} stop={t.stop} rr={t.rr_ratio}"
        )
        if t.supporting_factors:
            lines.append(f"    supporting: {', '.join(t.supporting_factors)}")
    ind = _daily_ind(analysis)
    if ind:
        lines.append("")
        lines.append("## Daily indicators")
        # NOTE: RSI is intentionally omitted — it's an oscillator, not classical charting,
        # and must not influence the alpha decision.
        lines.append(
            f"- trend_template_pass={ind.trend_template_pass}; "
            f"close={ind.close:.2f} sma50={ind.sma50} sma150={ind.sma150} sma200={ind.sma200}; "
            f"pct_from_52w_high={ind.pct_from_52w_high}; pct_above_sma50={ind.pct_above_sma50}; "
            f"atr_pct={ind.atr_pct}"
        )
    wk = _weekly_ind(analysis)
    if wk and wk.sma200 is not None:
        rel = "ABOVE" if wk.close >= wk.sma200 else "BELOW"
        lines.append(
            f"- long-term: weekly close {wk.close:.2f} is {rel} the 200-week SMA "
            f"({wk.sma200:.2f})"
        )
    lines.append("")
    lines.append("## Market regime + sector")
    if regime is not None:
        lines.append(
            f"- regime: {regime.overall_state.value}; posture: {regime.long_posture.value}; "
            f"mood: {regime.mood}"
        )
    lines.append(
        f"- sector '{sector}' leadership: "
        f"{sector_status.value if sector_status else 'unknown'}"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- deterministic gate

# Conviction weights. Positive signals sum to 100 when everything lines up; penalties
# subtract. R:R and RSI deliberately carry NO weight (R:R: stops are subjective; RSI: an
# oscillator, not classical charting). Near-highs and sector-leadership are PLUS-ONLY
# (their absence is never a minus). Below-200-week and extreme-extension are penalties.
_W_TREND = 30  # Stage-2 trend-template (hard gate)
_W_REGIME = 18  # risk-on market regime (hard gate)
_W_SETUP = 17  # an actionable setup with a trigger (hard gate)
_W_NEAR_HIGH = 13  # at / near the 52-week high (plus)
_W_NEW_HIGH = 7  # making new highs — extra plus on top of near-high
_W_SECTOR_LEAD = 15  # a leading sector matching the stock (plus)
_PEN_BELOW_200W = 12  # below the 200-week SMA — long-term repairing / dead-cat risk
_PEN_EXTENDED = 10  # extreme extension above the 50-day MA


def _gate(
    analysis: TickerAnalysis,
    regime: RegimeSnapshot | None,
    sector: str,
    sector_status: Bias | None,
) -> AlphaVerdict:
    ind = _daily_ind(analysis)
    wk = _weekly_ind(analysis)
    th = _best_thesis(analysis)
    reasons: list[AlphaReason] = []

    # --- HARD gates: ALL must hold for an alpha ---
    tt = bool(ind and ind.trend_template_pass)
    reasons.append(
        AlphaReason(
            category="Trend",
            detail="Trend-template intact (Stage 2)" if tt else "Trend template not intact",
            status=Bias.BULLISH if tt else Bias.BEARISH,
        )
    )

    regime_ok = bool(
        regime and regime.overall_state in _RISK_ON and regime.long_posture in _OK_POSTURE
    )
    regime_align = (
        f"{regime.overall_state.value} / {regime.long_posture.value}" if regime else "unknown"
    )
    reasons.append(
        AlphaReason(
            category="Regime",
            detail=f"Market regime {regime_align}",
            status=Bias.BULLISH if regime_ok else Bias.BEARISH,
        )
    )

    tradeable = bool(
        th and th.entry is not None and th.status.value in ("forming", "confirmed", "triggered")
    )
    reasons.append(
        AlphaReason(
            category="Pattern",
            detail=(
                f"{th.pattern_label} ({th.status.value})" if th else "no actionable setup / trigger"
            ),
            status=Bias.BULLISH if tradeable else Bias.NEUTRAL,
        )
    )

    # --- SOFT signals: move conviction, never veto ---
    # Near / at highs — a PLUS; being far from highs is NOT a minus.
    pfh = ind.pct_from_52w_high if ind else None
    near_high = pfh is not None and pfh >= -8.0
    new_high = pfh is not None and pfh >= -0.5
    reasons.append(
        AlphaReason(
            category="Relative strength",
            detail=(
                f"At / near the 52-week high ({pfh:+.0f}%)"
                if near_high
                else (
                    f"{pfh:+.0f}% from the 52-week high (not a negative)"
                    if pfh is not None
                    else "distance from highs unknown"
                )
            ),
            status=Bias.BULLISH if near_high else Bias.NEUTRAL,
        )
    )

    # Sector leadership — a PLUS when the sector is leading; otherwise no effect either way.
    sector_lead = sector_status == Bias.BULLISH
    reasons.append(
        AlphaReason(
            category="Sector",
            detail=(
                f"Sector '{sector}' is leading — tailwind"
                if sector_lead
                else (
                    f"Sector '{sector}' not currently leading (no effect on the judgment)"
                    if sector_status is not None
                    else "Sector untagged — judged on the stock's own strength (not penalized)"
                )
            ),
            status=Bias.BULLISH if sector_lead else Bias.NEUTRAL,
        )
    )

    # Below the 200-week SMA — a PENALTY (long-term still repairing; dead-cat-bounce risk).
    below_200w = bool(wk and wk.sma200 is not None and wk.close < wk.sma200)
    if below_200w and wk and wk.sma200 is not None:
        reasons.append(
            AlphaReason(
                category="Long-term trend",
                detail=(
                    f"Below the 200-week SMA ({wk.sma200:.0f}) — long-term still repairing; "
                    "needs more proof (dead-cat-bounce risk)"
                ),
                status=Bias.BEARISH,
            )
        )

    # Extreme extension above the 50-day MA — a PENALTY.
    pct50 = ind.pct_above_sma50 if ind else None
    extended = pct50 is not None and pct50 > 25.0
    if extended and pct50 is not None:
        reasons.append(
            AlphaReason(
                category="Extension",
                detail=f"Extended {pct50:.0f}% above the 50-day MA",
                status=Bias.BEARISH,
            )
        )

    is_alpha = tt and regime_ok and tradeable
    conviction = max(
        0,
        min(
            100,
            (_W_TREND if tt else 0)
            + (_W_REGIME if regime_ok else 0)
            + (_W_SETUP if tradeable else 0)
            + (_W_NEAR_HIGH if near_high else 0)
            + (_W_NEW_HIGH if new_high else 0)
            + (_W_SECTOR_LEAD if sector_lead else 0)
            - (_PEN_BELOW_200W if below_200w else 0)
            - (_PEN_EXTENDED if extended else 0),
        ),
    )

    # entry/stop/target/rr are kept for the trade plan only — NOT a gate (stops are subjective).
    rr = th.rr_ratio if th else None
    if rr is None and th:
        rr = _rr(th.entry, th.stop, th.target)

    return AlphaVerdict(
        symbol=analysis.symbol,
        is_alpha=bool(is_alpha),
        conviction=conviction,
        stage="Stage 2" if tt else "not Stage 2",
        sector=sector,
        regime_alignment=regime_align,
        entry=th.entry if th else None,
        stop=th.stop if th else None,
        target=th.target if th else None,
        rr=rr,
        reasons=reasons,
        summary=(
            f"{'ALPHA' if is_alpha else 'Not alpha'} (conviction {conviction}): Stage-2 trend "
            f"{'OK' if tt else 'no'}, risk-on regime {'OK' if regime_ok else 'no'}, "
            f"actionable setup {'OK' if tradeable else 'no'} (deterministic)."
        ),
        source="deterministic",
    )


# --------------------------------------------------------------------------- LLM parse


def _coerce_bias(s: str) -> Bias:
    v = str(s).strip().lower()
    return Bias.BULLISH if v == "bullish" else (Bias.BEARISH if v == "bearish" else Bias.NEUTRAL)


def _num(v: object) -> float | None:
    if isinstance(v, int | float):
        return float(v)
    return None


def _parse(raw: str, symbol: str, sector: str) -> AlphaVerdict | None:
    if "{" not in raw or "}" not in raw:
        return None
    try:
        data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "is_alpha" not in data:
        return None
    summary = str(data.get("summary", "")).strip()
    if not summary:
        return None
    entry, stop, target = _num(data.get("entry")), _num(data.get("stop")), _num(data.get("target"))
    reasons = [
        AlphaReason(
            category=str(r.get("category", "")),
            detail=str(r.get("detail", "")),
            status=_coerce_bias(r.get("status", "neutral")),
        )
        for r in data.get("reasons", [])
        if isinstance(r, dict)
    ]
    conviction = int(_num(data.get("conviction")) or 0)
    return AlphaVerdict(
        symbol=symbol,
        is_alpha=bool(data.get("is_alpha")),
        conviction=max(0, min(100, conviction)),
        stage=str(data.get("stage", "")),
        sector=sector,
        regime_alignment=str(data.get("regime_alignment", "")),
        entry=entry,
        stop=stop,
        target=target,
        rr=_rr(entry, stop, target),
        reasons=reasons,
        summary=summary,
        source="llm",
    )


# --------------------------------------------------------- public (agent2 / agent3)


def decide_alpha_verdict(
    analysis: TickerAnalysis,
    regime: RegimeSnapshot | None,
    sector: str,
    analyst: LLMAnalyst,
    *,
    sector_status: Bias | None = None,
) -> AlphaVerdict:
    """agent2: judge whether `analysis` is an alpha opportunity (LLM, deterministic fallback).
    `sector_status` (fresh sector leadership) overrides the regime snapshot when provided."""
    ss = sector_status if sector_status is not None else _sector_status(regime, sector)
    digest = build_alpha_digest(analysis, regime, sector, ss)
    raw = ""
    try:
        raw = analyst.synthesize(ALPHA_SYSTEM, digest)
    except Exception as exc:  # noqa: BLE001 - never let the judge break the pipeline
        logger.warning("alpha synthesize raised: %s", exc)
    verdict = _parse(raw, analysis.symbol, sector) if raw else None
    if verdict is None:
        if raw:
            logger.warning("alpha LLM output unparseable; using deterministic gate")
        verdict = _gate(analysis, regime, sector, ss)
    verdict.inputs = digest
    return verdict


def rejudge_alpha_verdict(
    new_analysis: TickerAnalysis,
    prior: AlphaVerdict,
    regime: RegimeSnapshot | None,
    sector: str,
    analyst: LLMAnalyst,
    *,
    sector_status: Bias | None = None,
) -> AlphaVerdict:
    """agent3: re-evaluate an alpha name given fresh analysis + the prior verdict."""
    ss = sector_status if sector_status is not None else _sector_status(regime, sector)
    digest = build_alpha_digest(new_analysis, regime, sector, ss) + (
        f"\n\n## PRIOR VERDICT\n- is_alpha={prior.is_alpha}; conviction={prior.conviction}; "
        f"stage={prior.stage}; summary={prior.summary}"
    )
    raw = ""
    try:
        raw = analyst.synthesize(ALPHA_REFRESH_SYSTEM, digest)
    except Exception as exc:  # noqa: BLE001
        logger.warning("alpha rejudge synthesize raised: %s", exc)
    verdict = _parse(raw, new_analysis.symbol, sector) if raw else None
    if verdict is None:
        verdict = _gate(new_analysis, regime, sector, ss)
    verdict.inputs = digest
    return verdict
