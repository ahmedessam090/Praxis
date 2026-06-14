"""Chunk E: agent3 re-judge + persist (update vs downgrade) via ActivityEnvironment."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from temporalio.testing import ActivityEnvironment

import ta_assistant.temporal.activities.screener as screener_mod
from ta_assistant.screener import repo
from ta_assistant.synthesis.schema import (
    AlphaItem,
    AlphaVerdict,
    AnalysisSummary,
    Bias,
    TickerAnalysis,
    Timeframe,
)

NOW = datetime(2026, 6, 13, tzinfo=UTC)


class _Fake:
    def __init__(self, text: str) -> None:
        self.text = text

    def run_thesis_loop(self, **kw: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def synthesize(self, system: str, user: str) -> str:
        return self.text


def _analysis(symbol: str) -> TickerAnalysis:
    return TickerAnalysis(
        symbol=symbol,
        generated_at=NOW,
        timeframes=[Timeframe.DAILY],
        summary=AnalysisSummary(overall_bias=Bias.BULLISH, headline="x", price_now=100.0),
    )


def _seed_alpha(symbol: str, conviction: int) -> None:
    repo.upsert_alpha(
        AlphaItem(
            symbol=symbol,
            verdict=AlphaVerdict(
                symbol=symbol, is_alpha=True, conviction=conviction, summary="was alpha"
            ),
            analysis_generated_at=NOW,
            updated_at=NOW,
        )
    )


async def test_refresh_downgrades(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_alpha("TEST", 80)
    raw = json.dumps(
        {"is_alpha": False, "conviction": 15, "reasons": [], "summary": "broke down, lost RS"}
    )
    monkeypatch.setattr(screener_mod, "get_analyst", lambda settings=None: _Fake(raw))

    env = ActivityEnvironment()
    verdict = await env.run(screener_mod.rejudge_alpha, _analysis("TEST"))
    assert not verdict.is_alpha
    result = await env.run(
        screener_mod.persist_refresh_result, verdict, NOW.isoformat(), NOW.isoformat()
    )
    assert result == "downgraded"
    assert repo.get_alpha("TEST") is None
    dn = repo.list_downgraded()
    assert len(dn) == 1 and dn[0].symbol == "TEST"
    assert dn[0].prior_conviction == 80 and dn[0].downgrade_reason


async def test_refresh_keeps_alpha(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_alpha("KEEP", 70)
    raw = json.dumps(
        {"is_alpha": True, "conviction": 88, "reasons": [], "summary": "still leading, holding up"}
    )
    monkeypatch.setattr(screener_mod, "get_analyst", lambda settings=None: _Fake(raw))

    env = ActivityEnvironment()
    verdict = await env.run(screener_mod.rejudge_alpha, _analysis("KEEP"))
    result = await env.run(
        screener_mod.persist_refresh_result, verdict, NOW.isoformat(), NOW.isoformat()
    )
    assert result == "alpha"
    item = repo.get_alpha("KEEP")
    assert item is not None and item.verdict.conviction == 88
    assert not repo.list_downgraded()
