"""persist_analysis writes idempotently across a simulated retry (same dedup key)."""

from __future__ import annotations

import dataclasses
import json

import sqlalchemy as sa
from temporalio.activity import Info
from temporalio.testing import ActivityEnvironment

from ta_assistant.db.session import get_engine
from ta_assistant.temporal.activities.persist import persist_analysis


def _info_with_workflow_id(env: ActivityEnvironment, workflow_id: str) -> Info:
    return dataclasses.replace(env.default_info(), workflow_id=workflow_id)


async def test_persist_analysis_is_idempotent(temp_db: str) -> None:
    env = ActivityEnvironment()
    # attempt 1 and a simulated retry (attempt 2) share the same workflow_id.
    # ActivityEnvironment.info is the ActivityInfo VALUE returned by activity.info().
    env.info = _info_with_workflow_id(env, "wf-123")

    key1 = await env.run(persist_analysis, "AAPL", {"sma": 2.0})
    key2 = await env.run(persist_analysis, "AAPL", {"sma": 2.0})

    assert key1 == key2 == "wf-123:analysis"

    with get_engine(temp_db).connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM analyses")).scalar()
        payload = conn.execute(sa.text("SELECT payload_json FROM analyses")).scalar()

    assert count == 1  # second run was a no-op
    assert json.loads(str(payload))["sma"] == 2.0
