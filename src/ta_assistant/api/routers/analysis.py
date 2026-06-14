"""Ticker Analysis endpoints: latest stored analysis (from DB) + trigger/poll +
OHLCV bars for client-side candlestick charts."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

from ta_assistant.api.deps import temporal_client, workflow_status
from ta_assistant.config import get_settings
from ta_assistant.data.analysis_repo import latest_analysis
from ta_assistant.data.bars_repo import load_bars
from ta_assistant.synthesis.schema import TickerAnalysis
from ta_assistant.temporal.workflows.analyze_ticker import AnalyzeTickerWorkflow

router = APIRouter(prefix="/api", tags=["analysis"])

_TF_CODE = {"daily": "D", "weekly": "W", "monthly": "M"}


class Candle(BaseModel):
    time: int  # UNIX seconds (lightweight-charts native)
    open: float
    high: float
    low: float
    close: float
    volume: float


class RefreshRequest(BaseModel):
    symbol: str


@router.get("/bars")
async def bars(symbol: str, timeframe: str = "daily", limit: int = 520) -> list[Candle]:
    """OHLCV for client-side candlestick rendering (most-recent `limit` bars)."""
    code = _TF_CODE.get(timeframe.lower(), "D")
    df = await asyncio.to_thread(load_bars, symbol.upper(), code)
    if limit and len(df) > limit:
        df = df.iloc[-limit:]
    return [
        Candle(
            time=int(pd.Timestamp(ts).timestamp()),
            open=round(float(r.open), 4),
            high=round(float(r.high), 4),
            low=round(float(r.low), 4),
            close=round(float(r.close), 4),
            volume=float(r.volume),
        )
        for ts, r in df.iterrows()
    ]


@router.get("/analysis/{symbol}")
async def analysis_latest(symbol: str) -> TickerAnalysis | None:
    return await asyncio.to_thread(latest_analysis, symbol)


@router.post("/analysis/refresh")
async def analysis_refresh(req: RefreshRequest) -> dict[str, str]:
    client = await temporal_client()
    settings = get_settings()
    sym = req.symbol.upper()
    handle = await client.start_workflow(
        AnalyzeTickerWorkflow.run,
        sym,
        id=f"analyze-{sym}-{uuid4().hex[:8]}",
        task_queue=settings.temporal_task_queue,
    )
    return {"workflow_id": handle.id}


@router.get("/analysis/status/{workflow_id}")
async def analysis_status(workflow_id: str) -> dict[str, str]:
    return {"status": await workflow_status(workflow_id)}
