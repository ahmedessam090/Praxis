"""Shared API dependencies: a process-cached Temporal client + workflow status helper."""

from __future__ import annotations

import asyncio

from temporalio.client import Client

from ta_assistant.temporal.client import get_client

_client: Client | None = None
_lock = asyncio.Lock()


async def temporal_client() -> Client:
    """One connected client per process (lazily created, reused across requests)."""
    global _client
    if _client is None:
        async with _lock:
            if _client is None:
                _client = await get_client()
    return _client


async def workflow_status(workflow_id: str) -> str:
    """Status name of a workflow run (RUNNING | COMPLETED | FAILED | …), or UNKNOWN."""
    client = await temporal_client()
    desc = await client.get_workflow_handle(workflow_id).describe()
    return desc.status.name if desc.status is not None else "UNKNOWN"
