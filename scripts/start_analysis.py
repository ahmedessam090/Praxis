"""Kick off a CandidateAnalysisWorkflow and wait for its result.

Requires the Temporal stack up (`make temporal-up`) and a worker running
(`make worker`). Usage:
    uv run python scripts/start_analysis.py [SYMBOL]
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from ta_assistant.config import get_settings
from ta_assistant.temporal.client import get_client
from ta_assistant.temporal.workflows.candidate_analysis import CandidateAnalysisWorkflow


async def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    settings = get_settings()
    client = await get_client()
    wf_id = f"analysis-{symbol}-{uuid.uuid4().hex[:8]}"

    handle = await client.start_workflow(
        CandidateAnalysisWorkflow.run,
        symbol,
        id=wf_id,
        task_queue=settings.temporal_task_queue,
    )
    print(f"started workflow id={wf_id}; waiting for result...")
    result = await handle.result()
    print(f"result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
