"""MarketRegimeWorkflow — the durable market-conditions read (manual trigger).

Pure orchestration: fan out the data fetch by symbol group (reusing the bars cache),
then compute the 5 pillars + charts + the integrated LLM mood, then persist the whole
snapshot. All I/O + LLM work lives in the activities; now / workflow_id come from the
deterministic workflow APIs. fetch_groups() is a pure deterministic constant list.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ta_assistant.regime.universe import fetch_groups
    from ta_assistant.synthesis.schema import RegimeSnapshot
    from ta_assistant.temporal.activities.regime import (
        build_regime_snapshot,
        fetch_regime_bars,
        persist_regime,
    )

_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class MarketRegimeWorkflow:
    @workflow.run
    async def run(self) -> RegimeSnapshot:
        now_iso = workflow.now().isoformat()
        workflow_id = workflow.info().workflow_id

        fetched: list[list[str]] = list(
            await asyncio.gather(
                *(
                    workflow.execute_activity(
                        fetch_regime_bars,
                        args=[group, now_iso],
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=_RETRY,
                    )
                    for group in fetch_groups()
                )
            )
        )
        symbols = sorted({s for group in fetched for s in group})

        snapshot = await workflow.execute_activity(
            build_regime_snapshot,
            args=[symbols, now_iso],
            start_to_close_timeout=timedelta(minutes=8),
            retry_policy=_RETRY,
        )
        await workflow.execute_activity(
            persist_regime,
            args=[snapshot, workflow_id],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=_RETRY,
        )
        return snapshot
