"""Market Regime endpoints: latest snapshot (from DB) + trigger/poll the workflow."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter

from ta_assistant.api.deps import temporal_client, workflow_status
from ta_assistant.config import get_settings
from ta_assistant.regime.repo import latest_regime
from ta_assistant.synthesis.schema import RegimeSnapshot
from ta_assistant.temporal.workflows.market_regime import MarketRegimeWorkflow

router = APIRouter(prefix="/api/regime", tags=["regime"])


@router.get("/latest")
async def regime_latest() -> RegimeSnapshot | None:
    """The most recent persisted regime snapshot (input charts + metrics + conclusion)."""
    return await asyncio.to_thread(latest_regime)


@router.post("/refresh")
async def regime_refresh() -> dict[str, str]:
    """Start a fresh MarketRegimeWorkflow; returns the workflow id to poll."""
    client = await temporal_client()
    settings = get_settings()
    handle = await client.start_workflow(
        MarketRegimeWorkflow.run,
        id=f"regime-{uuid4().hex[:10]}",
        task_queue=settings.temporal_task_queue,
    )
    return {"workflow_id": handle.id}


@router.get("/status")
async def regime_status(workflow_id: str) -> dict[str, str]:
    return {"status": await workflow_status(workflow_id)}
