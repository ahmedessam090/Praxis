"""End-to-end AlphaCandidateWorkflow: child AnalyzeTickerWorkflow (agent1) -> agent2 verdict
-> persist. Mocked data + NullAnalyst for agent1; a fake LLM for the alpha verdict."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

import ta_assistant.temporal.activities.analysis as analysis_mod
import ta_assistant.temporal.activities.screener as screener_mod
from ta_assistant.analyst.provider import NullAnalyst
from ta_assistant.data.analysis_repo import latest_analysis
from ta_assistant.screener import repo
from ta_assistant.synthesis.schema import CandidateStatus, ScreenerCandidate
from ta_assistant.temporal.activities import ALL_ACTIVITIES
from ta_assistant.temporal.sandbox import SANDBOX_RESTRICTIONS
from ta_assistant.temporal.workflows import ALL_WORKFLOWS
from ta_assistant.temporal.workflows.alpha import AlphaCandidateWorkflow

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 13, tzinfo=UTC)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _uptrend() -> pd.DataFrame:
    c = np.array([50.0 + 0.4 * i for i in range(320)], dtype=float)
    idx = pd.bdate_range("2023-01-02", periods=len(c))
    return pd.DataFrame(
        {
            "open": c,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": np.full(len(c), 2_000_000.0),
            "raw_close": c,
            "adj_factor": np.ones(len(c)),
        },
        index=idx,
    )


class _FakeAlpha:
    def run_thesis_loop(self, **kw: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def synthesize(self, system: str, user: str) -> str:
        return json.dumps(
            {
                "is_alpha": True,
                "conviction": 85,
                "stage": "Stage 2 breakout",
                "regime_alignment": "n/a",
                "entry": None,
                "stop": None,
                "target": None,
                "reasons": [{"category": "Trend", "detail": "leader", "status": "bullish"}],
                "summary": "Clear leader breaking out — alpha.",
            }
        )


async def test_alpha_pipeline_end_to_end(
    temp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analysis_mod, "get_daily_history", lambda s: (_uptrend(), "mock"))
    monkeypatch.setattr(analysis_mod, "get_analyst", lambda settings=None: NullAnalyst())
    monkeypatch.setattr(analysis_mod, "fetch_earnings_info", lambda symbol, today: None)
    monkeypatch.setattr(screener_mod, "get_analyst", lambda settings=None: _FakeAlpha())

    repo.upsert_candidates(
        [
            ScreenerCandidate(
                symbol="TEST", sector="technology", score=50.0, source="screen", generated_at=NOW
            )
        ]
    )

    async with await WorkflowEnvironment.start_local(
        port=_free_port(), data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="tq-alpha",
            workflows=ALL_WORKFLOWS,
            activities=ALL_ACTIVITIES,
            workflow_runner=SandboxedWorkflowRunner(restrictions=SANDBOX_RESTRICTIONS),
        ):
            count = await env.client.execute_workflow(
                AlphaCandidateWorkflow.run, ["TEST"], id="wf-alpha-1", task_queue="tq-alpha"
            )

    assert count == 1
    item = repo.get_alpha("TEST")
    assert item is not None and item.verdict.is_alpha and item.verdict.source == "llm"
    assert item.verdict.conviction == 85
    cand = repo.get_candidate("TEST")
    assert cand is not None and cand.status is CandidateStatus.ALPHA
    # the candidate carries the verdict + the exact inputs the agent saw (Scanner "Why?")
    assert cand.verdict is not None and cand.verdict.is_alpha
    assert "ALPHA EVALUATION" in (cand.verdict.inputs or "")
    # the child AnalyzeTickerWorkflow persisted the analysis (powers the alpha detail view)
    assert latest_analysis("TEST") is not None
