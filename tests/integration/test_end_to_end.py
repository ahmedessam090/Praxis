"""End-to-end: real workflow + real activities against a local dev server,
persisting one analysis row to a temp SQLite DB."""

from __future__ import annotations

import socket

import pytest
import sqlalchemy as sa
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from ta_assistant.db.session import get_engine
from ta_assistant.temporal.activities import ALL_ACTIVITIES
from ta_assistant.temporal.workflows import ALL_WORKFLOWS
from ta_assistant.temporal.workflows.candidate_analysis import CandidateAnalysisWorkflow

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def test_end_to_end_persists_analysis(temp_db: str) -> None:
    async with await WorkflowEnvironment.start_local(port=_free_port()) as env:
        task_queue = "tq-e2e"
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=ALL_WORKFLOWS,
            activities=ALL_ACTIVITIES,
        ):
            result = await env.client.execute_workflow(
                CandidateAnalysisWorkflow.run,
                "MSFT",
                id="wf-e2e-1",
                task_queue=task_queue,
            )

    assert result["last"] == 106.0
    with get_engine(temp_db).connect() as conn:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM analyses WHERE symbol = 'MSFT'")
        ).scalar()
    assert count == 1
