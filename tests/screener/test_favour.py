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
    ranks = rank_sectors(frames)
    assert ranks[0].sector == "technology"
    assert ranks[0].rs_status == "bullish"
    assert ranks[-1].sector == "utilities"


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
