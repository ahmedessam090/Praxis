"""Transient activity failures retry per policy; completed activities are not re-run."""

from __future__ import annotations

from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from ta_assistant.temporal.workflows.candidate_analysis import CandidateAnalysisWorkflow

FAIL_TIMES = 2  # compute_indicators fails twice, succeeds on attempt 3


async def test_transient_failure_is_retried(workflow_env: Any) -> None:
    attempts = {"fetch_bars": 0, "compute_indicators": 0, "persist_analysis": 0}

    @activity.defn(name="fetch_bars")
    async def fetch_bars(symbol: str) -> list[float]:
        attempts["fetch_bars"] += 1
        return [10.0, 20.0, 30.0]

    @activity.defn(name="compute_indicators")
    async def compute_indicators(prices: list[float]) -> dict[str, float]:
        attempts["compute_indicators"] += 1
        if attempts["compute_indicators"] <= FAIL_TIMES:
            raise ApplicationError("transient data hiccup")  # retryable by default
        return {"sma": sum(prices) / len(prices), "last": prices[-1]}

    @activity.defn(name="persist_analysis")
    async def persist_analysis(symbol: str, indicators: dict[str, float]) -> str:
        attempts["persist_analysis"] += 1
        return f"{symbol}:analysis"

    task_queue = "tq-retry"
    async with Worker(
        workflow_env.client,
        task_queue=task_queue,
        workflows=[CandidateAnalysisWorkflow],
        activities=[fetch_bars, compute_indicators, persist_analysis],
    ):
        result = await workflow_env.client.execute_workflow(
            CandidateAnalysisWorkflow.run,
            "AAPL",
            id="wf-retry-1",
            task_queue=task_queue,
        )

    assert result["last"] == 30.0
    # compute_indicators retried until success...
    assert attempts["compute_indicators"] == FAIL_TIMES + 1
    # ...while the already-completed first activity was NOT re-run.
    assert attempts["fetch_bars"] == 1
    assert attempts["persist_analysis"] == 1
