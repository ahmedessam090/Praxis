"""Screener API: candidate CRUD, alpha list, trigger endpoints (mocked Temporal), jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

import ta_assistant.api.routers.screener as screener_router
from ta_assistant.api.app import app
from ta_assistant.screener import repo
from ta_assistant.synthesis.schema import (
    AlphaItem,
    AlphaVerdict,
    ScreenerCandidate,
)

client = TestClient(app)
NOW = datetime(2026, 6, 13, tzinfo=UTC)


class _Handle:
    id = "wf-screen-123"


class _FakeClient:
    async def start_workflow(self, *a: Any, **k: Any) -> _Handle:
        return _Handle()


async def _fake_client() -> _FakeClient:
    return _FakeClient()


def _cand(symbol: str, sector: str = "technology") -> ScreenerCandidate:
    return ScreenerCandidate(symbol=symbol, sector=sector, score=50.0, generated_at=NOW)


def _alpha(symbol: str) -> AlphaItem:
    return AlphaItem(
        symbol=symbol,
        verdict=AlphaVerdict(symbol=symbol, is_alpha=True, conviction=80, summary="x"),
        analysis_generated_at=NOW,
        updated_at=NOW,
    )


def test_candidates_crud(temp_db: str) -> None:
    assert client.get("/api/screener/candidates").json() == []
    repo.upsert_candidates([_cand("AAPL"), _cand("MSFT")])
    body = client.get("/api/screener/candidates").json()
    assert {c["symbol"] for c in body} == {"AAPL", "MSFT"}
    client.delete("/api/screener/candidates/AAPL")
    assert {c["symbol"] for c in client.get("/api/screener/candidates").json()} == {"MSFT"}
    assert client.delete("/api/screener/candidates").json() == {"cleared": 1}
    assert client.get("/api/screener/candidates").json() == []


def test_add_candidate_manual(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        screener_router, "build_manual_candidate", lambda sym, now: _cand("TSLA", "discretionary")
    )
    body = client.post("/api/screener/candidates", json={"symbol": "tsla"}).json()
    assert body["symbol"] == "TSLA"
    assert any(c.symbol == "TSLA" for c in repo.list_candidates())


def test_add_candidate_invalid_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screener_router, "build_manual_candidate", lambda sym, now: None)
    r = client.post("/api/screener/candidates", json={"symbol": "zzzz"})
    assert r.status_code == 400


def test_alpha_and_downgraded_lists(temp_db: str) -> None:
    assert client.get("/api/screener/alpha").json() == []
    assert client.get("/api/screener/downgraded").json() == []
    repo.upsert_alpha(_alpha("NVDA"))
    body = client.get("/api/screener/alpha").json()
    assert body[0]["symbol"] == "NVDA" and body[0]["verdict"]["conviction"] == 80


def test_scan_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screener_router, "temporal_client", _fake_client)
    assert client.post("/api/screener/scan").json() == {"workflow_id": "wf-screen-123"}


def test_evaluate_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screener_router, "temporal_client", _fake_client)
    body = client.post("/api/screener/alpha/evaluate", json={"symbols": ["aapl", "nvda"]}).json()
    assert body["workflow_id"] == "wf-screen-123"


def test_refresh_all_resolves_alpha(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    repo.upsert_alpha(_alpha("NVDA"))
    captured: dict[str, Any] = {}

    class _CapClient:
        async def start_workflow(self, run: Any, *args: Any, **k: Any) -> _Handle:
            captured["args"] = args
            return _Handle()

    monkeypatch.setattr(screener_router, "temporal_client", lambda: _wrap(_CapClient()))
    body = client.post("/api/screener/alpha/refresh", json={"symbols": []}).json()
    assert body["workflow_id"] == "wf-screen-123"
    assert captured["args"] == (["NVDA"],)  # refresh-all resolved the current alpha list


async def _wrap(c: Any) -> Any:
    return c


def test_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _running(wt: str) -> bool:
        return wt == "ScannerWorkflow"

    monkeypatch.setattr(screener_router, "is_running", _running)
    assert client.get("/api/screener/jobs").json() == {
        "scan": True,
        "evaluate": False,
        "refresh": False,
    }
