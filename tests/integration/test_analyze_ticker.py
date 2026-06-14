"""End-to-end AnalyzeTickerWorkflow: sandbox-validated workflow + real activities
(mocked data provider + NullAnalyst) -> theses, synthesis, charts on disk, persisted row."""

from __future__ import annotations

import socket
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import sqlalchemy as sa
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

import ta_assistant.temporal.activities.analysis as analysis_mod
from ta_assistant.analyst.provider import NullAnalyst
from ta_assistant.db.session import get_engine
from ta_assistant.temporal.activities import ALL_ACTIVITIES
from ta_assistant.temporal.sandbox import SANDBOX_RESTRICTIONS
from ta_assistant.temporal.workflows import ALL_WORKFLOWS
from ta_assistant.temporal.workflows.analyze_ticker import AnalyzeTickerWorkflow

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _double_bottom_daily() -> pd.DataFrame:
    # Ends mid-move (between neckline 105 and target 120) so the pattern is CURRENT
    # under the new relevance filter (not already run past target).
    targets, steps = [120, 90, 105, 90, 112], 30
    closes = [float(targets[0])]
    for t in targets[1:]:
        closes += np.linspace(closes[-1], float(t), steps + 1)[1:].tolist()
    c = np.asarray(closes, dtype=float)
    idx = pd.bdate_range("2015-01-01", periods=len(c))
    return pd.DataFrame(
        {
            "open": c,
            "high": c + 0.5,
            "low": c - 0.5,
            "close": c,
            "volume": np.full(len(c), 1_000_000.0),
            "raw_close": c,
            "adj_factor": np.ones(len(c)),
        },
        index=idx,
    )


async def test_analyze_ticker_end_to_end(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        analysis_mod, "get_daily_history", lambda symbol: (_double_bottom_daily(), "mock")
    )
    monkeypatch.setattr(analysis_mod, "get_analyst", lambda settings=None: NullAnalyst())
    monkeypatch.setattr(analysis_mod, "fetch_earnings_info", lambda symbol, today: None)

    async with await WorkflowEnvironment.start_local(
        port=_free_port(), data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="tq-analyze",
            workflows=ALL_WORKFLOWS,
            activities=ALL_ACTIVITIES,
            workflow_runner=SandboxedWorkflowRunner(restrictions=SANDBOX_RESTRICTIONS),
        ):
            result = await env.client.execute_workflow(
                AnalyzeTickerWorkflow.run,
                "TEST",
                id="wf-analyze-1",
                task_queue="tq-analyze",
            )

    assert result.symbol == "TEST"
    assert result.summary.price_now == pytest.approx(112, abs=2)

    # the engine detects the double bottom, now tagged SUPPORT (context, not a trade)
    daily = [p for p in result.patterns if p.timeframe.value == "daily"]
    db = next((p for p in daily if p.pattern_type == "double_bottom"), None)
    assert db is not None and db.tier == "support"

    # a thesis per timeframe, all labelled; the double bottom surfaces as a SUPPORTING factor
    assert result.theses
    assert all(t.pattern_label for t in result.theses)
    daily_thesis = next((t for t in result.theses if t.timeframe.value == "daily"), None)
    assert daily_thesis is not None
    assert any("double bottom" in f for f in daily_thesis.supporting_factors)
    # cross-timeframe synthesis was set and drove the summary
    assert result.synthesis is not None
    assert result.summary.headline

    # one static chart per timeframe on disk; one persisted row
    assert result.charts
    assert all(Path(c.png_path).exists() for c in result.charts)

    with get_engine(temp_db).connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM analyses WHERE symbol='TEST'")).scalar()
    assert count == 1
