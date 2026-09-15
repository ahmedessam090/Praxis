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


def test_candidates_sorted_by_updated_at_desc(temp_db: str) -> None:
    # The table shows most-recently-touched first, so a manually-added ticker lands on top.
    from sqlalchemy import text

    from ta_assistant.db.session import session_scope

    repo.upsert_candidates([_cand("AAPL"), _cand("MSFT"), _cand("NVDA")])
    stamps = {  # raw SQL so the ORM's onupdate=now() doesn't clobber our test timestamps
        "AAPL": "2026-06-15 00:00:00",
        "NVDA": "2026-06-15 00:05:00",
        "MSFT": "2026-06-15 00:10:00",  # most recently touched
    }
    with session_scope() as s:
        for sym, ts in stamps.items():
            s.execute(
                text("UPDATE screener_candidates SET updated_at = :ts WHERE symbol = :sym"),
                {"ts": ts, "sym": sym},
            )
    order = [c["symbol"] for c in client.get("/api/screener/candidates").json()]
    assert order == ["MSFT", "NVDA", "AAPL"]


def test_add_candidate_manual(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        screener_router,
        "build_manual_candidate",
        lambda sym, now, group="", *a: _cand("TSLA", "discretionary"),
    )
    body = client.post("/api/screener/candidates", json={"symbol": "tsla"}).json()
    assert body["symbol"] == "TSLA"
    assert any(c.symbol == "TSLA" for c in repo.list_candidates())


def test_add_candidate_invalid_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        screener_router, "build_manual_candidate", lambda sym, now, group="", *a: None
    )
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
    body = client.post("/api/screener/scan").json()
    assert body["workflow_id"] == "wf-screen-123"
    assert body["group"].startswith("Rally screen")  # auto-named rally-screen group


def test_groups_crud(temp_db: str) -> None:
    assert client.get("/api/screener/groups").json() == []
    assert client.post("/api/screener/groups", json={"name": "My AI plays"}).status_code == 200
    repo.upsert_candidates([_cand("AAPL")])  # not in the group
    g = client.post("/api/screener/groups", json={"name": "Watchlist"}).json()
    assert g["name"] == "Watchlist" and g["kind"] == "custom"
    names = {x["name"] for x in client.get("/api/screener/groups").json()}
    assert names == {"My AI plays", "Watchlist"}
    assert client.delete("/api/screener/groups/Watchlist").json() == {"removed": 0}
    assert {x["name"] for x in client.get("/api/screener/groups").json()} == {"My AI plays"}


def test_candidates_filtered_by_group(temp_db: str) -> None:
    repo.create_group("G1")
    repo.upsert_candidates(
        [
            _cand("AAPL").model_copy(update={"group": "G1"}),
            _cand("MSFT").model_copy(update={"group": "G2"}),
        ]
    )
    g1 = client.get("/api/screener/candidates", params={"group": "G1"}).json()
    assert {c["symbol"] for c in g1} == {"AAPL"}


def test_ai_pick_into_group(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screener_router, "propose_for_query", lambda *a, **k: ["NVDA", "AVGO"])
    monkeypatch.setattr(
        screener_router,
        "build_manual_candidate",
        lambda sym, now, group="", *a: _cand(sym).model_copy(update={"group": group}),
    )
    body = client.post(
        "/api/screener/ai-pick", json={"query": "AI infra leaders", "group": "AI infra"}
    ).json()
    assert body["added"] == 2 and body["group"] == "AI infra"
    assert {c.symbol for c in repo.list_candidates(group="AI infra")} == {"NVDA", "AVGO"}


def test_evaluate_trigger(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
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
