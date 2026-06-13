"""Dev tool: (re)generate the golden workflow history used by the replay test.

Run after an INTENTIONAL change to CandidateAnalysisWorkflow's orchestration:

    uv run python scripts/gen_golden_history.py

Uses a local dev server (no Rosetta needed) and mocked activities (no DB / keys).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from ta_assistant.temporal.workflows.candidate_analysis import CandidateAnalysisWorkflow

OUT = Path(__file__).resolve().parent.parent / "tests" / "histories" / "candidate_v1.json"


@activity.defn(name="fetch_bars")
async def fetch_bars(symbol: str) -> list[float]:
    return [10.0, 20.0, 30.0]


@activity.defn(name="compute_indicators")
async def compute_indicators(prices: list[float]) -> dict[str, float]:
    return {"sma": 20.0, "last": 30.0}


@activity.defn(name="persist_analysis")
async def persist_analysis(symbol: str, indicators: dict[str, float]) -> str:
    return f"{symbol}:analysis"


async def main() -> None:
    async with await WorkflowEnvironment.start_local() as env:
        task_queue = "tq-gen"
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[CandidateAnalysisWorkflow],
            activities=[fetch_bars, compute_indicators, persist_analysis],
        ):
            handle = await env.client.start_workflow(
                CandidateAnalysisWorkflow.run,
                "AAPL",
                id="wf-golden",
                task_queue=task_queue,
            )
            await handle.result()
            history = await handle.fetch_history()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(history.to_json())
    print(f"wrote golden history -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
