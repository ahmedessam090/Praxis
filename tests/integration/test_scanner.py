"""End-to-end ScannerWorkflow: fetch (mocked) -> favour-pick -> persist, deduped vs
already-tracked symbols. NullAnalyst ⇒ LLM augmentation no-ops."""

from __future__ import annotations

import socket
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

import ta_assistant.temporal.activities.screener as screener_mod
from ta_assistant.analyst.provider import NullAnalyst
from ta_assistant.db.models import DowngradedItemRow
from ta_assistant.db.session import session_scope
from ta_assistant.screener import repo
from ta_assistant.synthesis.schema import CandidateStatus
from ta_assistant.temporal.activities import ALL_ACTIVITIES
from ta_assistant.temporal.sandbox import SANDBOX_RESTRICTIONS
from ta_assistant.temporal.workflows import ALL_WORKFLOWS
from ta_assistant.temporal.workflows.scanner import ScannerWorkflow

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _frame(values: list[float]) -> pd.DataFrame:
    c = np.array(values, dtype=float)
    idx = pd.bdate_range("2023-01-02", periods=len(c))
    return pd.DataFrame(
        {
            "open": c,
            "high": c * 1.005,
            "low": c * 0.995,
            "close": c,
            "volume": np.full(len(c), 2e6),
        },
        index=idx,
    )


def _hist(symbol: str) -> tuple[pd.DataFrame, str]:
    n = 260
    if symbol == "SPY":
        return _frame([400.0] * n), "mock"  # flat benchmark -> uptrends show positive RS
    return _frame([50.0 + 0.4 * i for i in range(n)]), "mock"  # uptrend


async def test_scanner_end_to_end(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screener_mod, "get_daily_history", _hist)
    monkeypatch.setattr(screener_mod, "get_analyst", lambda settings=None: NullAnalyst())

    # NVDA is already downgraded -> the scan must NOT re-suggest it (cross-table dedup).
    with session_scope() as s:
        s.add(
            DowngradedItemRow(
                symbol="NVDA", payload_json="{}", downgraded_at=datetime(2026, 6, 1, tzinfo=UTC)
            )
        )

    async with await WorkflowEnvironment.start_local(
        port=_free_port(), data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="tq-scan",
            workflows=ALL_WORKFLOWS,
            activities=ALL_ACTIVITIES,
            workflow_runner=SandboxedWorkflowRunner(restrictions=SANDBOX_RESTRICTIONS),
        ):
            count = await env.client.execute_workflow(
                ScannerWorkflow.run, id="wf-scan-1", task_queue="tq-scan"
            )

    assert count > 0
    cands = repo.list_candidates()
    assert cands and len(cands) <= 40
    syms = {c.symbol for c in cands}
    assert "NVDA" not in syms  # deduped against the downgraded list
    assert all(c.status is CandidateStatus.PENDING and c.source == "screen" for c in cands)
    assert len({c.sector for c in cands}) > 1  # variety across sectors
    assert cands == sorted(cands, key=lambda c: c.score, reverse=True)  # ranked
