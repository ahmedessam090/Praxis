"""Alpha screener endpoints: scan, candidate management, push-to-alpha, the alpha list,
refresh/downgrade, and the downgraded list. Triggers/polls the durable workflows; reads
come from the screener repo. Alpha detail reuses GET /api/analysis/{symbol} + /api/bars."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ta_assistant.analyst.provider import get_analyst
from ta_assistant.api.deps import is_running, temporal_client, workflow_status
from ta_assistant.config import get_settings
from ta_assistant.screener import repo
from ta_assistant.screener.augment import propose_for_query
from ta_assistant.screener.manual import build_manual_candidate
from ta_assistant.synthesis.schema import (
    AlphaItem,
    CandidateStatus,
    DowngradedItem,
    ScreenerCandidate,
    ScreenerGroup,
)
from ta_assistant.temporal.workflows.alpha import AlphaCandidateWorkflow, AlphaRefreshWorkflow
from ta_assistant.temporal.workflows.scanner import ScannerWorkflow

router = APIRouter(prefix="/api/screener", tags=["screener"])


class SymbolsRequest(BaseModel):
    symbols: list[str] = []


class AddRequest(BaseModel):
    symbol: str
    group: str = ""


class CreateGroupRequest(BaseModel):
    name: str


class AiPickRequest(BaseModel):
    query: str
    group: str = ""
    limit: int = 10


def _qid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


# --- jobs (button-disable state) ---


@router.get("/jobs")
async def jobs() -> dict[str, bool]:
    """Which trigger types are currently running (so the UI can disable buttons)."""
    scan, evaluate, refresh = await asyncio.gather(
        is_running("ScannerWorkflow"),
        is_running("AlphaCandidateWorkflow"),
        is_running("AlphaRefreshWorkflow"),
    )
    return {"scan": scan, "evaluate": evaluate, "refresh": refresh}


@router.get("/status")
async def status(workflow_id: str) -> dict[str, str]:
    return {"status": await workflow_status(workflow_id)}


# --- scanner ---


@router.post("/scan")
async def scan(group: str = "") -> dict[str, str]:
    """Rally-screen: shallow-screen the rallying sectors and drop the hits into a group. The
    group name is auto-generated when not given; the persist activity creates the group."""
    g = group.strip() or f"Rally screen {datetime.now(UTC):%b %d %H:%M}"
    client = await temporal_client()
    handle = await client.start_workflow(
        ScannerWorkflow.run, g, id=_qid("scan"), task_queue=get_settings().temporal_task_queue
    )
    return {"workflow_id": handle.id, "group": g}


# --- groups (custom-groups model) ---


@router.get("/groups")
async def groups() -> list[ScreenerGroup]:
    return await asyncio.to_thread(repo.list_groups)


@router.post("/groups")
async def create_group(req: CreateGroupRequest) -> ScreenerGroup:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="group name required")
    await asyncio.to_thread(repo.create_group, name, "custom")
    return ScreenerGroup(name=name, kind="custom", count=0)


@router.delete("/groups/{name}")
async def delete_group(name: str) -> dict[str, int]:
    return {"removed": await asyncio.to_thread(repo.delete_group, name)}


@router.get("/candidates")
async def candidates(group: str | None = None) -> list[ScreenerCandidate]:
    return await asyncio.to_thread(repo.list_candidates, group)


@router.post("/candidates")
async def add_candidate(req: AddRequest) -> ScreenerCandidate:
    """Manually add a ticker (into a group when given): validate + score it like a scan hit."""
    cand = await asyncio.to_thread(
        build_manual_candidate, req.symbol, datetime.now(UTC), req.group
    )
    if cand is None:
        raise HTTPException(
            status_code=400, detail=f"Couldn't fetch data for '{req.symbol.upper()}'"
        )
    if req.group.strip():
        await asyncio.to_thread(repo.create_group, req.group.strip(), "custom")
    await asyncio.to_thread(repo.upsert_candidates, [cand])
    return cand


@router.post("/ai-pick")
async def ai_pick(req: AiPickRequest) -> dict[str, object]:
    """AI pick: describe what you want; the LLM proposes liquid good-performers, each validated
    by a real data fetch + shallow-scored, dropped into a group. No-op without an LLM key."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="describe what you want to scan")
    group = req.group.strip() or f"AI: {query[:48]}"
    existing = await asyncio.to_thread(repo.existing_symbols)
    symbols = await asyncio.to_thread(
        propose_for_query, query, get_analyst(get_settings()), existing, max_total=req.limit
    )
    await asyncio.to_thread(repo.create_group, group, "ai")
    now = datetime.now(UTC)
    cands: list[ScreenerCandidate] = []
    for sym in symbols:  # sequential build (one DB writer) to avoid SQLite write contention
        cand = await asyncio.to_thread(build_manual_candidate, sym, now, group, "ai")
        if cand is not None:
            cands.append(cand)
    if cands:
        await asyncio.to_thread(repo.upsert_candidates, cands)
    return {"added": len(cands), "group": group, "symbols": [c.symbol for c in cands]}


@router.delete("/candidates/{symbol}")
async def delete_candidate(symbol: str) -> dict[str, str]:
    await asyncio.to_thread(repo.delete_candidate, symbol)
    return {"deleted": symbol.upper()}


@router.delete("/candidates")
async def clear_candidates() -> dict[str, int]:
    return {"cleared": await asyncio.to_thread(repo.clear_candidates)}


# --- alpha ---


@router.post("/alpha/evaluate")
async def evaluate(req: SymbolsRequest) -> dict[str, str]:
    syms = [s.upper() for s in req.symbols]
    # Mark pushed candidates in-flight so the Scanner tab shows they're being evaluated.
    for s in syms:
        await asyncio.to_thread(repo.set_candidate_status, s, CandidateStatus.EVALUATING)
    client = await temporal_client()
    handle = await client.start_workflow(
        AlphaCandidateWorkflow.run,
        syms,
        id=_qid("alpha-eval"),
        task_queue=get_settings().temporal_task_queue,
    )
    return {"workflow_id": handle.id}


@router.get("/alpha")
async def alpha() -> list[AlphaItem]:
    return await asyncio.to_thread(repo.list_alpha)


@router.delete("/alpha/{symbol}")
async def delete_alpha(symbol: str) -> dict[str, str]:
    await asyncio.to_thread(repo.delete_alpha, symbol)
    return {"deleted": symbol.upper()}


@router.post("/alpha/refresh")
async def refresh(req: SymbolsRequest) -> dict[str, str]:
    syms = [s.upper() for s in req.symbols]
    if not syms:  # refresh-all: resolve the current alpha list now
        syms = [i.symbol for i in await asyncio.to_thread(repo.list_alpha)]
    client = await temporal_client()
    handle = await client.start_workflow(
        AlphaRefreshWorkflow.run,
        syms,
        id=_qid("alpha-refresh"),
        task_queue=get_settings().temporal_task_queue,
    )
    return {"workflow_id": handle.id}


# --- downgraded ---


@router.get("/downgraded")
async def downgraded() -> list[DowngradedItem]:
    return await asyncio.to_thread(repo.list_downgraded)
