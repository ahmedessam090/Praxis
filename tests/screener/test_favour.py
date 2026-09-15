"""Chunk A: sector ranking + candidate pre-screen + favour-weighted picking."""

from __future__ import annotations

from datetime import UTC, datetime

import screener_synth as S

import ta_assistant.regime.universe as RU
from ta_assistant.regime.sectors import rank_sectors
from ta_assistant.screener.favour import pick_candidates, score_ticker
from ta_assistant.synthesis.schema import Bias, CandidateStatus

NOW = datetime(2026, 6, 13, tzinfo=UTC)


def test_rank_sectors_leader_first() -> None:
    frames = {
        RU.SPY: S.flat(val=400.0),
        "XLK": S.uptrend(start_val=150.0, step=0.6),  # technology leading
        "XLU": S.downtrend(start_val=80.0, step=-0.1),  # utilities lagging
    }
    ranks = rank_sectors(frames)  # defaults to the GICS map (screener behavior unchanged)
    assert ranks[0].sector == "technology"
    assert ranks[0].rs_status == "bullish"
    assert ranks[-1].sector == "utilities"


def test_rank_sectors_broad_map_surfaces_industry_leader() -> None:
    # With the broad LEADERSHIP map, a rallying industry (semiconductors) surfaces by name
    # instead of being buried inside technology.
    frames = {
        RU.SPY: S.flat(val=400.0),
        "SMH": S.uptrend(start_val=200.0, step=1.2),  # semis ripping
        "XLK": S.uptrend(start_val=150.0, step=0.2),  # tech mildly up
        "XLU": S.downtrend(start_val=80.0, step=-0.1),  # utilities lagging
    }
    ranks = rank_sectors(frames, RU.LEADERSHIP_ETF)
    assert ranks[0].sector == "semiconductors" and ranks[0].etf == "SMH"
    assert any(r.sector == "technology" for r in ranks)  # GICS groups still ranked too


def _trend(last, sma50, sma200, change_pct, above_200=True, rising=True):  # type: ignore[no-untyped-def]
    from ta_assistant.regime.metrics import SeriesTrend

    return SeriesTrend(
        last=last,
        sma50=sma50,
        sma200=sma200,
        above_200=above_200,
        rising=rising,
        change_pct=change_pct,
        status="bullish",
    )


def test_overheated_when_extended_above_50dma() -> None:
    # Classical: a confirmed leader >=12% above its 50-day MA is over-extended/climactic.
    from ta_assistant.regime.sectors import _extension_pct, _is_overheated

    t = _trend(115.0, 100.0, 90.0, 0.10)  # 15% above the 50-day MA, +10% 3m
    ext = _extension_pct(t)
    assert ext == 15.0 and _is_overheated(t, ext) is True


def test_overheated_when_vertical_3m() -> None:
    from ta_assistant.regime.sectors import _extension_pct, _is_overheated

    t = _trend(105.0, 102.0, 90.0, 0.35)  # only ~3% above 50d but +35% in 3 months
    assert _is_overheated(t, _extension_pct(t)) is True


def test_not_overheated_when_mild_or_not_in_uptrend() -> None:
    from ta_assistant.regime.sectors import _extension_pct, _is_overheated

    mild = _trend(103.0, 100.0, 90.0, 0.05)  # 3% above, +5% 3m — fine
    assert _is_overheated(mild, _extension_pct(mild)) is False
    bounce = _trend(115.0, 100.0, 120.0, 0.10, above_200=False)  # extended but below 200d
    assert _is_overheated(bounce, _extension_pct(bounce)) is False  # not a confirmed uptrend


def test_score_ticker_uptrend_qualifies() -> None:
    score, factors, ok = score_ticker(S.uptrend(), S.flat(val=400.0))
    assert ok and score > 40
    assert any(f.label == "Trend template" and f.status is Bias.BULLISH for f in factors)


def test_score_ticker_downtrend_rejected() -> None:
    _score, _factors, ok = score_ticker(S.downtrend(), S.flat(val=400.0))
    assert not ok


def test_pick_candidates_favours_leaders_dedup_variety() -> None:
    frames = {
        RU.SPY: S.flat(val=400.0),
        "XLK": S.uptrend(start_val=150.0, step=0.6),  # leading sector
        "XLU": S.flat(val=70.0),  # laggard sector
        # technology names (uptrends)
        "AAPL": S.uptrend(start_val=120.0, step=0.5),
        "MSFT": S.uptrend(start_val=200.0, step=0.7),
        # utilities name (uptrend, but laggard sector)
        "NEE": S.uptrend(start_val=60.0, step=0.2),
    }
    cands = pick_candidates(frames, existing={"MSFT"}, now=NOW, n=30)
    syms = [c.symbol for c in cands]
    assert "AAPL" in syms  # picked from the leading sector
    assert "MSFT" not in syms  # deduped against existing
    assert "NEE" in syms  # variety — laggard sector still contributes
    # the leading-sector name outranks the laggard-sector name
    assert syms.index("AAPL") < syms.index("NEE")
    aapl = next(c for c in cands if c.symbol == "AAPL")
    assert aapl.sector == "technology" and aapl.status is CandidateStatus.PENDING
    assert aapl.factors
