"""Manual add: validate/score a ticker into a candidate; None when unfetchable."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import screener_synth as S

import ta_assistant.screener.manual as manual

NOW = datetime(2026, 6, 14, tzinfo=UTC)


def _hist(sym: str) -> Any:
    return (S.flat(val=400.0) if sym == "SPY" else S.uptrend()), "mock"


def test_build_manual_candidate(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manual, "get_daily_history", _hist)
    c = manual.build_manual_candidate("aapl", NOW)
    assert c is not None
    assert c.symbol == "AAPL" and c.sector == "technology" and c.source == "manual"
    assert c.factors  # scored like a scanned candidate


def test_build_manual_resolves_sector_via_lookup(
    temp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not in the curated universe -> falls back to the (mocked) yfinance sector lookup.
    monkeypatch.setattr(manual, "get_daily_history", _hist)
    monkeypatch.setattr(manual, "get_sector", lambda sym: "technology")
    c = manual.build_manual_candidate("AMKR", NOW)
    assert c is not None and c.sector == "technology"  # resolved, not "unknown"


def test_build_manual_unknown_sector(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # Curated map misses AND the lookup also fails -> only then "unknown".
    monkeypatch.setattr(manual, "get_daily_history", _hist)
    monkeypatch.setattr(manual, "get_sector", lambda sym: None)
    c = manual.build_manual_candidate("ZZZ", NOW)
    assert c is not None and c.symbol == "ZZZ" and c.sector == "unknown"


def test_map_yf_sector() -> None:
    from ta_assistant.data.yf import _map_yf_sector

    assert _map_yf_sector("Technology") == "technology"
    assert _map_yf_sector("Consumer Cyclical") == "discretionary"
    assert _map_yf_sector("financial-services") == "financials"
    assert _map_yf_sector("Healthcare") == "health"
    assert _map_yf_sector("real-estate") == "real_estate"
    assert _map_yf_sector("") is None and _map_yf_sector("Nonexistent") is None


def test_build_manual_unfetchable(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(sym: str) -> Any:
        raise RuntimeError("no such ticker")

    monkeypatch.setattr(manual, "get_daily_history", boom)
    assert manual.build_manual_candidate("NOPE", NOW) is None
