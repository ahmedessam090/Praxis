"""AlphaCandidateWorkflow — push selected scanner candidates through the real analysis.

Per selected symbol (fanned out): run the EXISTING AnalyzeTickerWorkflow as a CHILD (agent1,
which also persists the TickerAnalysis the alpha detail view reuses) -> agent2 alpha verdict
-> persist (onto the alpha list if alpha, else mark the candidate not-alpha).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ta_assistant.synthesis.schema import TickerAnalysis
    from ta_assistant.temporal.activities.screener import (
        decide_alpha,
        persist_alpha_result,
        persist_refresh_result,
        rejudge_alpha,
    )
    from ta_assistant.temporal.workflows.analyze_ticker import AnalyzeTickerWorkflow

_RETRY = RetryPolicy(maximum_attempts=2)


@workflow.defn
class AlphaCandidateWorkflow:
    @workflow.run
    async def run(self, symbols: list[str]) -> int:
        now_iso = workflow.now().isoformat()
        workflow_id = workflow.info().workflow_id
        results = list(
            await asyncio.gather(*(self._one(s, now_iso, workflow_id) for s in symbols))
        )
        return sum(1 for r in results if r)

    async def _one(self, symbol: str, now_iso: str, workflow_id: str) -> bool:
        analysis: TickerAnalysis = await workflow.execute_child_workflow(
            AnalyzeTickerWorkflow.run,
            symbol,
            id=f"alpha-{symbol}-{workflow_id}",
            execution_timeout=timedelta(minutes=30),
            retry_policy=_RETRY,
        )
        verdict = await workflow.execute_activity(
            decide_alpha,
            args=[analysis],
            start_to_close_timeout=timedelta(minutes=8),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            persist_alpha_result,
            args=[verdict, analysis.generated_at.isoformat(), now_iso],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=_RETRY,
        )
        return bool(verdict.is_alpha)


@workflow.defn
class AlphaRefreshWorkflow:
    """Re-run agent1 on alpha names, re-judge (agent3), and update or downgrade each."""

    @workflow.run
    async def run(self, symbols: list[str]) -> int:
        now_iso = workflow.now().isoformat()
        workflow_id = workflow.info().workflow_id
        results = list(
            await asyncio.gather(*(self._one(s, now_iso, workflow_id) for s in symbols))
        )
        return sum(1 for r in results if r)  # number still on the alpha list

    async def _one(self, symbol: str, now_iso: str, workflow_id: str) -> bool:
        analysis: TickerAnalysis = await workflow.execute_child_workflow(
            AnalyzeTickerWorkflow.run,
            symbol,
            id=f"refresh-{symbol}-{workflow_id}",
            execution_timeout=timedelta(minutes=30),
            retry_policy=_RETRY,
        )
        verdict = await workflow.execute_activity(
            rejudge_alpha,
            args=[analysis],
            start_to_close_timeout=timedelta(minutes=8),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            persist_refresh_result,
            args=[verdict, analysis.generated_at.isoformat(), now_iso],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=_RETRY,
        )
        return bool(verdict.is_alpha)
