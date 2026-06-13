"""Persistence activity — idempotent SQLite write.

Activities can run more than once (retry or post-crash resume), so the write is
idempotent on a stable dedup key derived from the workflow id (never from
attempt/now/random). The blocking DB call is offloaded to a thread so it doesn't
stall the worker's event loop.
"""

from __future__ import annotations

import asyncio
import json

from temporalio import activity

from ta_assistant.db.models import Analysis
from ta_assistant.db.session import session_scope


def _write(dedup_key: str, symbol: str, indicators: dict[str, float]) -> None:
    with session_scope() as session:
        if session.get(Analysis, dedup_key) is None:
            session.add(
                Analysis(
                    dedup_key=dedup_key,
                    symbol=symbol,
                    payload_json=json.dumps(indicators),
                )
            )


@activity.defn
async def persist_analysis(symbol: str, indicators: dict[str, float]) -> str:
    """Idempotently persist an analysis result; returns the dedup key."""
    dedup_key = f"{activity.info().workflow_id}:analysis"
    await asyncio.to_thread(_write, dedup_key, symbol, indicators)
    return dedup_key
