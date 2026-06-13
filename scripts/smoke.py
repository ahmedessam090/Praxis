"""End-to-end smoke check against the running Docker Temporal stack + domain DB.

Verifies, in order:
  1. Temporal frontend reachable + namespace exists,
  2. the SQLite domain DB is migrated,
  3. a real workflow runs client -> worker -> activity -> SQLite (needs `make worker`).

Run after `make temporal-up` + `make migrate`, with `make worker` running elsewhere:
    make smoke
"""

from __future__ import annotations

import asyncio
import uuid

import sqlalchemy as sa
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest

from ta_assistant.config import get_settings
from ta_assistant.db.session import get_engine
from ta_assistant.temporal.client import get_client
from ta_assistant.temporal.workflows.candidate_analysis import CandidateAnalysisWorkflow


async def main() -> int:
    settings = get_settings()

    # 1) Temporal frontend reachable + namespace exists.
    client = await get_client()
    await client.service_client.workflow_service.describe_namespace(
        DescribeNamespaceRequest(namespace=settings.temporal_namespace)
    )
    addr, ns = settings.temporal_address, settings.temporal_namespace
    print(f"[smoke] Temporal OK at {addr} (namespace '{ns}')")

    # 2) Domain DB migrated.
    tables = set(sa.inspect(get_engine(settings.db_path)).get_table_names())
    missing = {"workflow_runs", "analyses"} - tables
    if missing:
        print(f"[smoke] FAIL: DB not migrated, missing {missing} — run `make migrate`")
        return 1
    print(f"[smoke] DB migrated at {settings.db_path}: {sorted(tables)}")

    # 3) Real end-to-end workflow execution (needs a worker on the task queue).
    wf_id = f"smoke-{uuid.uuid4().hex[:8]}"
    try:
        result = await asyncio.wait_for(
            client.execute_workflow(
                CandidateAnalysisWorkflow.run,
                "SMOKE",
                id=wf_id,
                task_queue=settings.temporal_task_queue,
            ),
            timeout=30,
        )
    except TimeoutError:
        print("[smoke] FAIL: workflow did not complete in 30s — is `make worker` running?")
        return 1
    print(f"[smoke] workflow {wf_id} completed -> {result}")

    with get_engine(settings.db_path).connect() as conn:
        symbol = conn.execute(
            sa.text("SELECT symbol FROM analyses WHERE dedup_key = :k"),
            {"k": f"{wf_id}:analysis"},
        ).scalar()
    if symbol != "SMOKE":
        print(f"[smoke] FAIL: expected analysis row for {wf_id}, got {symbol!r}")
        return 1

    print("[smoke] OK: client -> Temporal -> worker -> activity -> SQLite verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
