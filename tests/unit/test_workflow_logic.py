"""CandidateAnalysisWorkflow orchestration with mocked activities (no real I/O)."""

from __future__ import annotations

from typing import Any

from temporalio import activity
from temporalio.worker import Worker

from ta_assistant.temporal.workflows.candidate_analysis import CandidateAnalysisWorkflow


async def test_candidate_analysis_happy_path(workflow_env: Any) -> None:
    calls = {"fetch": 0, "compute": 0, "persist": 0}

    @activity.defn(name="fetch_bars")
    async def fetch_bars(symbol: str) -> list[float]:
        calls["fetch"] += 1
        return [10.0, 20.0, 30.0]

    @activity.defn(name="compute_indicators")
    async def compute_indicators(prices: list[float]) -> dict[str, float]:
        calls["compute"] += 1
        return {"sma": sum(prices) / len(prices), "last": prices[-1]}

    @activity.defn(name="persist_analysis")
    async def persist_analysis(symbol: str, indicators: dict[str, float]) -> str:
        calls["persist"] += 1
        return f"{symbol}:analysis"

    task_queue = "tq-logic"
    async with Worker(
        workflow_env.client,
        task_queue=task_queue,
        workflows=[CandidateAnalysisWorkflow],
        activities=[fetch_bars, compute_indicators, persist_analysis],
    ):
        result = await workflow_env.client.execute_workflow(
            CandidateAnalysisWorkflow.run,
            "AAPL",
            id="wf-logic-1",
            task_queue=task_queue,
        )

    assert result == {"sma": 20.0, "last": 30.0}
    assert calls == {"fetch": 1, "compute": 1, "persist": 1}
