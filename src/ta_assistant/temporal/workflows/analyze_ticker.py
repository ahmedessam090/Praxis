"""AnalyzeTickerWorkflow — the durable single-ticker analysis pipeline.

Pure orchestration: build (fetch + deterministic seed) -> per-timeframe AI chartist loop
(fan-out, one durable activity each) -> cross-timeframe synthesis -> render -> persist.
All LLM/tool work lives inside the activities; the workflow only sequences them. now /
workflow_id come from the deterministic workflow APIs (never wall-clock).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ta_assistant.synthesis.schema import TickerAnalysis, TimeframeThesis
    from ta_assistant.temporal.activities.analysis import (
        analyze_timeframe,
        build_analysis,
        persist_analysis_result,
        render_charts,
        synthesize,
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

        # Fan out the AI chartist over each timeframe (deterministic list -> deterministic
        # fan-out). Each loop is one durable, retried, cached activity.
        theses: list[TimeframeThesis] = list(
            await asyncio.gather(
                *(
                    workflow.execute_activity(
                        analyze_timeframe,
                        args=[analysis, tf, workflow_id],
                        start_to_close_timeout=timedelta(minutes=12),
                        retry_policy=_RETRY,
                    )
                    for tf in analysis.timeframes
                )
            )
        )

        analysis = await workflow.execute_activity(
            synthesize,
            args=[analysis, theses],
            start_to_close_timeout=timedelta(minutes=4),
            retry_policy=_RETRY,
        )
        analysis = await workflow.execute_activity(
            render_charts,
            args=[analysis, workflow_id],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            persist_analysis_result,
            args=[analysis, workflow_id],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=_RETRY,
        )
        return analysis
