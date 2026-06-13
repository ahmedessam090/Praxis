"""Sample analysis pipeline, shaped like the real Phase-1 work.

Pure orchestration: fetch bars -> compute indicators -> (durable timer) -> persist.
Phase 1 fills the activities with real provider/indicator/pattern logic; the
orchestration shape stays the same.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ta_assistant.temporal.activities.market import compute_indicators, fetch_bars
    from ta_assistant.temporal.activities.persist import persist_analysis


@workflow.defn
class CandidateAnalysisWorkflow:
    @workflow.run
    async def run(self, symbol: str) -> dict[str, float]:
        prices = await workflow.execute_activity(
            fetch_bars,
            symbol,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )

        indicators = await workflow.execute_activity(
            compute_indicators,
            prices,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=5,
            ),
        )

        # Durable timer: survives worker death; on resume execution continues here.
        await workflow.sleep(timedelta(seconds=2))

        await workflow.execute_activity(
            persist_analysis,
            args=[symbol, indicators],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )
        return indicators
