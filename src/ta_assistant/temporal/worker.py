"""Worker entry point: `python -m ta_assistant.temporal.worker`.

Registers all workflows + activities on the configured task queue and runs until
killed. The crash-recovery test spawns this as a subprocess and SIGKILLs it.
"""

from __future__ import annotations

import asyncio
import logging

from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

from ta_assistant.config import get_settings
from ta_assistant.temporal.activities import ALL_ACTIVITIES
from ta_assistant.temporal.client import get_client
from ta_assistant.temporal.sandbox import SANDBOX_RESTRICTIONS
from ta_assistant.temporal.workflows import ALL_WORKFLOWS

logger = logging.getLogger("ta_assistant.worker")


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    client = await get_client()
    logger.info(
        "Worker connecting address=%s namespace=%s queue=%s",
        settings.temporal_address,
        settings.temporal_namespace,
        settings.temporal_task_queue,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=ALL_WORKFLOWS,
        activities=ALL_ACTIVITIES,
        workflow_runner=SandboxedWorkflowRunner(restrictions=SANDBOX_RESTRICTIONS),
    )
    async with worker:
        logger.info("Worker started; waiting for tasks (Ctrl-C / SIGKILL to stop).")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
