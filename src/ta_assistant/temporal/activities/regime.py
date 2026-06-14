"""Market Regime activities — all I/O + LLM work for the regime read.

fetch (fan-out, reuses the bars cache) -> build snapshot (deterministic metrics + charts +
LLM mood via the analyst abstraction, cached) -> persist (idempotent). Blocking work is
offloaded with asyncio.to_thread; pydantic models round-trip via the data converter.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from temporalio import activity

from ta_assistant.analyst.cache import cache_get, cache_put, content_hash
from ta_assistant.analyst.prompts import PROMPT_VERSION
from ta_assistant.analyst.provider import get_analyst
from ta_assistant.config import Settings, get_settings
from ta_assistant.data.bars_repo import load_bars, upsert_bars
from ta_assistant.data.providers import get_daily_history
from ta_assistant.regime.charts import build_charts
from ta_assistant.regime.narrative import RegimeRead, build_digest, synthesize_regime_read
from ta_assistant.regime.pillars import assess, state_label
from ta_assistant.regime.repo import persist_snapshot
from ta_assistant.synthesis.schema import RegimeSnapshot

# ~3 trading years — enough for the 200-day MA, 52-week levels, the 30-week Weinstein
# stage and the ~2yr charts. Keeps each write transaction short so the fanned-out fetch
# activities don't hold the SQLite write lock long enough to contend.
_REGIME_HISTORY_BARS = 820


def _fetch(symbols: list[str]) -> list[str]:
    done: list[str] = []
    for sym in symbols:
        try:
            df, source = get_daily_history(sym)
        except Exception as exc:  # noqa: BLE001 - a missing symbol must not fail the regime
            activity.logger.warning("regime fetch failed for %s: %s", sym, exc)
            continue
        if len(df) > 0:
            if len(df) > _REGIME_HISTORY_BARS:
                df = df.iloc[-_REGIME_HISTORY_BARS:]
            upsert_bars(df, sym, "D", source)
            done.append(sym)
    return done


@activity.defn
async def fetch_regime_bars(symbols: list[str], now_iso: str) -> list[str]:
    """Fetch + cache daily bars for a bucket of symbols; returns the ones that succeeded."""
    return await asyncio.to_thread(_fetch, symbols)


def _model_name(s: Settings) -> str:
    if s.active_provider == "anthropic":
        return s.anthropic_model
    if s.active_provider == "openai":
        return s.openai_model
    return "none"


def _build_snapshot(symbols: list[str], now_iso: str) -> RegimeSnapshot:
    generated_at = datetime.fromisoformat(now_iso)
    now = generated_at.replace(tzinfo=None)
    frames = {}
    for sym in symbols:
        df = load_bars(sym, "D")
        if len(df) > 0:
            frames[sym] = df

    pillars, verdict = assess(frames, now)
    charts = build_charts(frames)

    settings = get_settings()
    analyst = get_analyst(settings)
    digest = build_digest(pillars, verdict)
    key = content_hash(
        {
            "kind": "regime",
            "digest": digest,
            "provider": settings.active_provider,
            "model": _model_name(settings),
            "prompt": PROMPT_VERSION,
        }
    )
    cached = cache_get(key, RegimeRead)
    if cached is not None and cached.source == "llm":
        read = cached
    else:
        read = synthesize_regime_read(pillars, verdict, analyst)
        if read.source == "llm":
            cache_put(key, _model_name(settings), read)

    return RegimeSnapshot(
        generated_at=generated_at,
        overall_state=read.state,
        long_posture=read.posture,
        mood=read.mood,
        score=round(verdict.score, 3),
        headline=f"{state_label(read.state)} — {read.posture.value} long posture",
        narrative=read.narrative,
        source=read.source,
        pillars=pillars,
        charts=charts,
    )


@activity.defn
async def build_regime_snapshot(symbols: list[str], now_iso: str) -> RegimeSnapshot:
    """Compute the 5 pillars + charts (deterministic) and the integrated mood (LLM, cached,
    deterministic fallback) into one self-contained snapshot."""
    return await asyncio.to_thread(_build_snapshot, symbols, now_iso)


@activity.defn
async def persist_regime(snapshot: RegimeSnapshot, workflow_id: str) -> str:
    """Idempotently persist the full snapshot (data + conclusion); returns the dedup key."""
    dedup_key = f"{workflow_id}:regime"
    await asyncio.to_thread(persist_snapshot, snapshot, dedup_key)
    return dedup_key
