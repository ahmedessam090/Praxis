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


def test_build_manual_unknown_sector(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manual, "get_daily_history", _hist)
    c = manual.build_manual_candidate("ZZZ", NOW)  # not in the curated universe
    assert c is not None and c.symbol == "ZZZ" and c.sector == "unknown"


def test_build_manual_unfetchable(temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(sym: str) -> Any:
        raise RuntimeError("no such ticker")

    monkeypatch.setattr(manual, "get_daily_history", boom)
    assert manual.build_manual_candidate("NOPE", NOW) is None
