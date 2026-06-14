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
    """Status name of a workflow run (RUNNING | COMPLETED | FAILED | …), or UNKNOWN.
    Returns UNKNOWN (not a 500) if the handle can't be described (bad id / transient RPC)."""
    client = await temporal_client()
    try:
        desc = await client.get_workflow_handle(workflow_id).describe()
    except Exception:  # noqa: BLE001 - surface a pollable status, not a 500
        return "UNKNOWN"
    return desc.status.name if desc.status is not None else "UNKNOWN"


async def is_running(workflow_type: str) -> bool:
    """True if any workflow of `workflow_type` is currently Running (for disabling
    trigger buttons). Best-effort: returns False if visibility isn't available."""
    client = await temporal_client()
    try:
        query = f"WorkflowType = '{workflow_type}' AND ExecutionStatus = 'Running'"
        async for _ in client.list_workflows(query):
            return True
        return False
    except Exception:  # noqa: BLE001 - never let a visibility hiccup block the UI
        return False
