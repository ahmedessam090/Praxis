"""FastAPI endpoints: latest reads from DB, refresh returns a workflow id (mocked
Temporal), bars serialize to UNIX-time candles. No real Temporal server needed."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import ta_assistant.api.routers.analysis as analysis_router
import ta_assistant.api.routers.regime as regime_router
from ta_assistant.api.app import app
from ta_assistant.data.bars_repo import upsert_bars
from ta_assistant.regime.repo import persist_snapshot
from ta_assistant.synthesis.schema import (
    LongPosture,
    RegimePillar,
    RegimeSnapshot,
    RegimeState,
)

client = TestClient(app)


class _Handle:
    id = "wf-mock-123"


class _FakeClient:
    async def start_workflow(self, *a: Any, **k: Any) -> _Handle:
        return _Handle()


async def _fake_client() -> _FakeClient:
    return _FakeClient()


def _snap() -> RegimeSnapshot:
    return RegimeSnapshot(
        generated_at=datetime(2026, 6, 13, tzinfo=UTC),
        overall_state=RegimeState.CONFIRMED_UPTREND,
        long_posture=LongPosture.SELECTIVE,
        mood="Risk-on",
        score=0.4,
        headline="Confirmed Uptrend",
        narrative="up",
        source="deterministic",
        pillars=[RegimePillar(key="primary_trend", name="Primary Trend")],
    )


def test_health() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_regime_latest_empty(temp_db: str) -> None:
    assert client.get("/api/regime/latest").json() is None


def test_regime_latest_after_persist(temp_db: str) -> None:
    persist_snapshot(_snap(), "wf-1:regime")
    body = client.get("/api/regime/latest").json()
    assert body["overall_state"] == "confirmed_uptrend"
    assert body["long_posture"] == "selective"
    assert body["pillars"][0]["key"] == "primary_trend"


def test_regime_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(regime_router, "temporal_client", _fake_client)
    body = client.post("/api/regime/refresh").json()
    assert body["workflow_id"] == "wf-mock-123"


def test_regime_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _status(wid: str) -> str:
        return "RUNNING"

    monkeypatch.setattr(regime_router, "workflow_status", _status)
    body = client.get("/api/regime/status", params={"workflow_id": "x"}).json()
    assert body["status"] == "RUNNING"


def test_analysis_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_router, "temporal_client", _fake_client)
    body = client.post("/api/analysis/refresh", json={"symbol": "aapl"}).json()
    assert body["workflow_id"] == "wf-mock-123"


def test_analysis_latest_empty(temp_db: str) -> None:
    assert client.get("/api/analysis/NVDA").json() is None


def test_bars(temp_db: str) -> None:
    idx = pd.bdate_range("2024-01-02", periods=5, name="ts")
    df = pd.DataFrame(
        {
            "open": [10, 11, 12, 13, 14.0],
            "high": [10.5, 11.5, 12.5, 13.5, 14.5],
            "low": [9.5, 10.5, 11.5, 12.5, 13.5],
            "close": [10.2, 11.2, 12.2, 13.2, 14.2],
            "volume": [1e6] * 5,
        },
        index=idx,
    )
    upsert_bars(df, "AAPL", "D", "mock")
    rows = client.get("/api/bars", params={"symbol": "AAPL", "timeframe": "daily"}).json()
    assert len(rows) == 5
    assert isinstance(rows[0]["time"], int) and 1_000_000_000 < rows[0]["time"] < 2_000_000_000
    assert {"open", "high", "low", "close", "volume"} <= rows[0].keys()
