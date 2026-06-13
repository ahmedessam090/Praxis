"""Crash-recovery demo workflow: a single long activity.

`heartbeat_timeout` keeps recovery fast — when the worker dies, heartbeats stop,
the server times out the attempt within a few seconds, and the retry policy
re-dispatches the activity to a fresh worker (which no-ops the idempotent side
effect). The workflow run_id is unchanged: it resumes, it does not restart.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ta_assistant.temporal.activities.crash_demo import long_running_step


@workflow.defn
class CrashDemoWorkflow:
    @workflow.run
    async def run(self, work_dir: str) -> str:
        return await workflow.execute_activity(
            long_running_step,
            work_dir,
            start_to_close_timeout=timedelta(seconds=60),
            heartbeat_timeout=timedelta(seconds=3),
            retry_policy=RetryPolicy(maximum_attempts=10),
        )
