"""ScannerWorkflow — find candidate tickers (manual trigger).

Pure orchestration: fan out the bars fetch by symbol group, then a deterministic
favour-pick + LLM-augment scan, then persist. Dedupes vs everything already tracked.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ta_assistant.screener.universe import screen_fetch_groups
    from ta_assistant.temporal.activities.screener import (
        fetch_screen_bars,
        persist_candidates,
        scan_candidates,
    )

_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class ScannerWorkflow:
    @workflow.run
    async def run(self, group: str = "") -> int:
        now_iso = workflow.now().isoformat()

        await asyncio.gather(
            *(
                workflow.execute_activity(
                    fetch_screen_bars,
                    args=[group, now_iso],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=_RETRY,
                )
                for group in screen_fetch_groups()
            )
        )
        candidates = await workflow.execute_activity(
            scan_candidates,
            args=[now_iso],
            start_to_close_timeout=timedelta(minutes=6),
            retry_policy=_RETRY,
        )
        return await workflow.execute_activity(
            persist_candidates,
            args=[candidates, group],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=_RETRY,
        )
