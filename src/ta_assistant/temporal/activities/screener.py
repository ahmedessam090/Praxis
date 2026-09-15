"""Alpha screener activities — scanning (this chunk) + the alpha pipeline (later chunks).

Scanning: fetch+cache bars for SPY/sector-ETFs/universe (fan-out), then deterministically
pick candidates favouring leading sectors + an LLM augmentation pass, then persist. All I/O;
blocking work offloaded with asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from temporalio import activity

from ta_assistant.analyst.cache import cache_get, cache_put, content_hash
from ta_assistant.analyst.pattern_judge import judge_patterns
from ta_assistant.analyst.prompts import ALPHA_RULES_VERSION, JUDGE_RULES_VERSION, PROMPT_VERSION
from ta_assistant.analyst.provider import get_analyst
from ta_assistant.config import Settings, get_settings
from ta_assistant.data.bars_repo import load_bars, upsert_bars
from ta_assistant.data.providers import get_daily_history
from ta_assistant.regime import universe as RU
from ta_assistant.regime.repo import latest_regime
from ta_assistant.regime.sectors import rank_sectors
from ta_assistant.screener import levels, repo
from ta_assistant.screener import universe as SU
from ta_assistant.screener.alpha import decide_alpha_verdict, rejudge_alpha_verdict
from ta_assistant.screener.augment import propose_extra
from ta_assistant.screener.favour import pick_candidates, score_ticker
from ta_assistant.synthesis.schema import (
    AlphaItem,
    AlphaVerdict,
    Bias,
    CandidateStatus,
    DowngradedItem,
    GapNote,
    KeyLevel,
    ScreenerCandidate,
    TickerAnalysis,
)

_HISTORY_BARS = 820  # ~3yr; keeps write txns short (avoids SQLite lock under fan-out)
_MAX_CANDIDATES = 40


def _fetch(symbols: list[str]) -> list[str]:
    done: list[str] = []
    for sym in symbols:
        try:
            df, source = get_daily_history(sym)
        except Exception as exc:  # noqa: BLE001 - a missing symbol must not fail the scan
            activity.logger.warning("screen fetch failed for %s: %s", sym, exc)
            continue
        if len(df) > 0:
            if len(df) > _HISTORY_BARS:
                df = df.iloc[-_HISTORY_BARS:]
            upsert_bars(df, sym, "D", source)
            done.append(sym)
    return done


@activity.defn
async def fetch_screen_bars(symbols: list[str], now_iso: str) -> list[str]:
    """Fetch + cache daily bars for a bucket of scan symbols; returns the ones that succeeded."""
    return await asyncio.to_thread(_fetch, symbols)


def _scan(now_iso: str) -> list[ScreenerCandidate]:
    now = datetime.fromisoformat(now_iso)
    existing = repo.existing_symbols()
    frames = {}
    for sym in SU.scan_symbols():
        df = load_bars(sym, "D")
        if len(df) > 0:
            frames[sym] = df

    cands = pick_candidates(frames, existing, now)

    # LLM augmentation — propose extra names in leading sectors, validate by real fetch.
    spy = frames.get(RU.SPY)
    if spy is not None and len(spy) > 0:
        analyst = get_analyst()
        ranks = rank_sectors(frames)
        considered = existing | {c.symbol for c in cands}
        for sym, sector in propose_extra(ranks, considered, analyst):
            try:
                df, source = get_daily_history(sym)
            except Exception:  # noqa: BLE001 - drop unfetchable / hallucinated tickers
                continue
            if len(df) < 200:
                continue
            df = df.iloc[-_HISTORY_BARS:] if len(df) > _HISTORY_BARS else df
            upsert_bars(df, sym, "D", source)
            score, factors, ok = score_ticker(df, spy)
            if ok:
                cands.append(
                    ScreenerCandidate(
                        symbol=sym,
                        sector=sector,
                        score=round(score, 2),
                        factors=factors,
                        source="llm",
                        generated_at=now,
                    )
                )

    cands.sort(key=lambda c: c.score, reverse=True)
    return cands[:_MAX_CANDIDATES]


@activity.defn
async def scan_candidates(now_iso: str) -> list[ScreenerCandidate]:
    """Deterministic favour-pick + LLM augment over the cached bars (dedupes vs existing)."""
    return await asyncio.to_thread(_scan, now_iso)


def _persist(cands: list[ScreenerCandidate], group: str) -> int:
    if group:  # rally-screen results land in a named group the user can review
        repo.create_group(group, kind="scan")
        for c in cands:
            c.group = group
    return repo.upsert_candidates(cands)


@activity.defn
async def persist_candidates(cands: list[ScreenerCandidate], group: str = "") -> int:
    """Idempotently upsert the scanned candidates (into `group` when given); count persisted."""
    return await asyncio.to_thread(_persist, cands, group)


# --- alpha pipeline (agent2) ---


def _model_name(s: Settings) -> str:
    if s.active_provider == "anthropic":
        return s.anthropic_model
    if s.active_provider == "openai":
        return s.openai_model
    return "none"


def _sector_for(symbol: str) -> str:
    cand = repo.get_candidate(symbol)
    if cand is not None:
        return cand.sector
    return SU.sector_of(symbol) or "unknown"


def _fresh_sector_status(sector: str) -> Bias | None:
    """Sector leadership computed FRESH from cached bars (not a possibly-stale regime
    snapshot), so the alpha agent always gets the current sector standing."""
    frames = {}
    for sym in [RU.SPY, *RU.SECTOR_ETFS]:
        df = load_bars(sym, "D")
        if len(df) > 0:
            frames[sym] = df
    for r in rank_sectors(frames):
        if r.sector == sector:
            return Bias(r.rs_status)
    return None


def _decide(analysis: TickerAnalysis) -> AlphaVerdict:
    settings = get_settings()
    sector = _sector_for(analysis.symbol)
    regime = latest_regime()
    ss = _fresh_sector_status(sector)
    fp = content_hash(
        {
            "kind": "alpha",
            "symbol": analysis.symbol,
            "generated_at": analysis.generated_at.isoformat(),
            "theses": [
                (t.timeframe.value, t.entry, t.target, t.stop, t.status.value, t.pattern_label)
                for t in analysis.theses
            ],
            "regime": regime.overall_state.value if regime else "none",
            "sector_status": ss.value if ss else "none",
            "provider": settings.active_provider,
            "model": _model_name(settings),
            "prompt": PROMPT_VERSION,
            "alpha_rules": ALPHA_RULES_VERSION,
            "judge_rules": JUDGE_RULES_VERSION,
        }
    )
    cached = cache_get(fp, AlphaVerdict)
    if cached is not None and cached.source == "llm":
        return cached
    analyst = get_analyst(settings)
    judge_patterns(analysis, analyst)  # vet the surfaced setup; demote an illegitimate one
    verdict = decide_alpha_verdict(analysis, regime, sector, analyst, sector_status=ss)
    if verdict.source == "llm":
        cache_put(fp, _model_name(settings), verdict)
    return verdict


@activity.defn
async def decide_alpha(analysis: TickerAnalysis) -> AlphaVerdict:
    """agent2: judge whether the analysed candidate is an alpha opportunity (cached)."""
    return await asyncio.to_thread(_decide, analysis)


def _attention(symbol: str) -> tuple[list[KeyLevel], list[GapNote]]:
    """Key price levels + notable gaps for an alpha name, from its daily bars.
    Returns empty lists when there are no bars (never raises)."""
    df = load_bars(symbol, "D")
    if len(df) == 0:
        return [], []
    return levels.attention(df)


def _persist_alpha(verdict: AlphaVerdict, analysis_generated_at_iso: str, now_iso: str) -> str:
    status = CandidateStatus.ALPHA if verdict.is_alpha else CandidateStatus.NOT_ALPHA
    repo.set_candidate_status(verdict.symbol, status, verdict)  # carry the verdict for the UI
    if verdict.is_alpha:
        key_levels, gaps = _attention(verdict.symbol)
        repo.upsert_alpha(
            AlphaItem(
                symbol=verdict.symbol,
                verdict=verdict,
                analysis_generated_at=datetime.fromisoformat(analysis_generated_at_iso),
                updated_at=datetime.fromisoformat(now_iso),
                levels=key_levels,
                gaps=gaps,
            )
        )
    return status.value


@activity.defn
async def persist_alpha_result(
    verdict: AlphaVerdict, analysis_generated_at_iso: str, now_iso: str
) -> str:
    """Set the candidate's status and (if alpha) upsert it onto the alpha list."""
    return await asyncio.to_thread(
        _persist_alpha, verdict, analysis_generated_at_iso, now_iso
    )


# --- refresh / downgrade pipeline (agent3) ---


def _rejudge(new_analysis: TickerAnalysis) -> AlphaVerdict:
    settings = get_settings()
    sector = _sector_for(new_analysis.symbol)
    regime = latest_regime()
    ss = _fresh_sector_status(sector)
    analyst = get_analyst(settings)
    judge_patterns(new_analysis, analyst)  # vet the surfaced setup; demote an illegitimate one
    existing = repo.get_alpha(new_analysis.symbol)
    if existing is None:  # not on the list yet — treat as a fresh decision
        return decide_alpha_verdict(new_analysis, regime, sector, analyst, sector_status=ss)
    return rejudge_alpha_verdict(
        new_analysis, existing.verdict, regime, sector, analyst, sector_status=ss
    )


@activity.defn
async def rejudge_alpha(new_analysis: TickerAnalysis) -> AlphaVerdict:
    """agent3: re-evaluate an alpha name given fresh analysis + its prior verdict."""
    return await asyncio.to_thread(_rejudge, new_analysis)


def _persist_refresh(verdict: AlphaVerdict, analysis_generated_at_iso: str, now_iso: str) -> str:
    now = datetime.fromisoformat(now_iso)
    existing = repo.get_alpha(verdict.symbol)
    if verdict.is_alpha:
        key_levels, gaps = _attention(verdict.symbol)
        repo.upsert_alpha(
            AlphaItem(
                symbol=verdict.symbol,
                verdict=verdict,
                analysis_generated_at=datetime.fromisoformat(analysis_generated_at_iso),
                updated_at=now,
                levels=key_levels,
                gaps=gaps,
            )
        )
        repo.set_candidate_status(verdict.symbol, CandidateStatus.ALPHA)
        return "alpha"
    # downgrade: drop from the alpha list, record why, mark the candidate — all atomically
    repo.move_to_downgraded(
        DowngradedItem(
            symbol=verdict.symbol,
            prior_conviction=existing.verdict.conviction if existing else verdict.conviction,
            prior_summary=existing.verdict.summary if existing else "",
            downgrade_reason=verdict.summary or "No longer qualifies as alpha.",
            downgraded_at=now,
        )
    )
    return "downgraded"


@activity.defn
async def persist_refresh_result(
    verdict: AlphaVerdict, analysis_generated_at_iso: str, now_iso: str
) -> str:
    """Update the alpha item, or move it to the downgraded list if it no longer qualifies."""
    return await asyncio.to_thread(
        _persist_refresh, verdict, analysis_generated_at_iso, now_iso
    )
