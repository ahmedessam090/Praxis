"""AnalyzeTickerWorkflow — the durable single-ticker analysis pipeline.

Pure orchestration: build (fetch+detect+summary) -> render charts -> LLM validate
-> persist. The TickerAnalysis is threaded through each activity. now/workflow_id
come from the deterministic workflow APIs (never wall-clock in workflow code).
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ta_assistant.synthesis.schema import TickerAnalysis
    from ta_assistant.temporal.activities.analysis import (
        build_analysis,
        persist_analysis_result,
        render_charts,
        validate_patterns,
    )

_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class AnalyzeTickerWorkflow:
    @workflow.run
    async def run(self, symbol: str) -> TickerAnalysis:
        now_iso = workflow.now().isoformat()
        workflow_id = workflow.info().workflow_id

        analysis = await workflow.execute_activity(
            build_analysis,
            args=[symbol, now_iso],
            start_to_close_timeout=timedelta(minutes=4),
            retry_policy=_RETRY,
        )
        analysis = await workflow.execute_activity(
            render_charts,
            args=[analysis, workflow_id],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=_RETRY,
        )
        analysis = await workflow.execute_activity(
            validate_patterns,
            args=[analysis],
            start_to_close_timeout=timedelta(minutes=4),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            persist_analysis_result,
            args=[analysis, workflow_id],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=_RETRY,
        )
        return analysis
