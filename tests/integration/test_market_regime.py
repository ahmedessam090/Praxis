"""End-to-end MarketRegimeWorkflow: sandbox-validated workflow + real activities (mocked
data provider) -> 5 pillars, charts, persisted snapshot (data + conclusion). One run uses
the deterministic NullAnalyst, one uses a fake LLM whose mood routes through the abstraction.
"""

from __future__ import annotations

import socket
from typing import Any

import numpy as np
import pandas as pd
import pytest
import sqlalchemy as sa
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

import ta_assistant.temporal.activities.regime as regime_mod
from ta_assistant.analyst.provider import NullAnalyst
from ta_assistant.db.session import get_engine
from ta_assistant.regime.repo import latest_regime
from ta_assistant.synthesis.schema import RegimeState
from ta_assistant.temporal.activities import ALL_ACTIVITIES
from ta_assistant.temporal.sandbox import SANDBOX_RESTRICTIONS
from ta_assistant.temporal.workflows import ALL_WORKFLOWS
from ta_assistant.temporal.workflows.market_regime import MarketRegimeWorkflow

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _uptrend(symbol: str) -> tuple[pd.DataFrame, str]:
    """A clean multi-year uptrend for every requested symbol -> confirmed-uptrend regime."""
    n = 340
    c = np.array([50.0 + 0.4 * i for i in range(n)], dtype=float)
    idx = pd.bdate_range("2023-01-02", periods=n)
    df = pd.DataFrame(
        {
            "open": c,
            "high": c * 1.005,
            "low": c * 0.995,
            "close": c,
            "volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )
    return df, "mock"


class _FakeLLM:
    """An analyst whose one-shot synthesize returns a canned regime JSON."""

    def run_thesis_loop(self, **kw: Any) -> Any:  # pragma: no cover - unused
        raise NotImplementedError

    def synthesize(self, system: str, user: str) -> str:
        return (
            '{"overall_state": "confirmed_uptrend", "long_posture": "aggressive", '
            '"mood": "Risk-on per the LLM", '
            '"narrative": "Broad advance; buy breakouts (LLM read)."}'
        )


async def _run(env: WorkflowEnvironment, wf_id: str) -> Any:
    async with Worker(
        env.client,
        task_queue="tq-regime",
        workflows=ALL_WORKFLOWS,
        activities=ALL_ACTIVITIES,
        workflow_runner=SandboxedWorkflowRunner(restrictions=SANDBOX_RESTRICTIONS),
    ):
        return await env.client.execute_workflow(
            MarketRegimeWorkflow.run, id=wf_id, task_queue="tq-regime"
        )


async def test_regime_end_to_end_deterministic(
    temp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(regime_mod, "get_daily_history", _uptrend)
    monkeypatch.setattr(regime_mod, "get_analyst", lambda settings=None: NullAnalyst())

    async with await WorkflowEnvironment.start_local(
        port=_free_port(), data_converter=pydantic_data_converter
    ) as env:
        result = await _run(env, "wf-regime-det")

    # 5 pillars, populated charts, a deterministic confirmed-uptrend read
    assert {p.key for p in result.pillars} == {
        "primary_trend",
        "supply_demand",
        "breadth",
        "intermarket",
        "volatility",
    }
    assert result.overall_state is RegimeState.CONFIRMED_UPTREND
    assert result.source == "deterministic"
    assert result.charts
    spx = next((c for c in result.charts if c.key == "spx"), None)
    assert spx is not None and any(s.kind == "candle" for s in spx.series)
    # a liquidity-cycle metric is always surfaced
    inter = next(p for p in result.pillars if p.key == "intermarket")
    assert any(m.key == "liquidity_cycle" for m in inter.metrics)

    # persisted whole (data + conclusion) and reloadable
    with get_engine(temp_db).connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM regime_snapshots")).scalar()
    assert count == 1
    reloaded = latest_regime(temp_db)
    assert reloaded is not None
    assert reloaded.overall_state is RegimeState.CONFIRMED_UPTREND
    assert reloaded.charts and reloaded.pillars


async def test_regime_mood_routes_through_llm(
    temp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(regime_mod, "get_daily_history", _uptrend)
    monkeypatch.setattr(regime_mod, "get_analyst", lambda settings=None: _FakeLLM())

    async with await WorkflowEnvironment.start_local(
        port=_free_port(), data_converter=pydantic_data_converter
    ) as env:
        result = await _run(env, "wf-regime-llm")

    assert result.source == "llm"
    assert result.mood == "Risk-on per the LLM"
    assert "LLM read" in result.narrative
