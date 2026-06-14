"""latest_analysis: serve the most-recent stored TickerAnalysis for a symbol."""

from __future__ import annotations

from datetime import UTC, datetime

from ta_assistant.data.analysis_repo import latest_analysis
from ta_assistant.db.models import Analysis
from ta_assistant.db.session import session_scope
from ta_assistant.synthesis.schema import AnalysisSummary, Bias, TickerAnalysis


def _analysis(symbol: str, price: float) -> TickerAnalysis:
    return TickerAnalysis(
        symbol=symbol,
        generated_at=datetime(2026, 6, 13, tzinfo=UTC),
        summary=AnalysisSummary(overall_bias=Bias.BULLISH, headline="up", price_now=price),
    )


def _store(symbol: str, price: float, dedup: str, when: datetime | None = None) -> None:
    with session_scope() as s:
        s.add(
            Analysis(
                dedup_key=dedup,
                symbol=symbol.upper(),
                payload_json=_analysis(symbol, price).model_dump_json(),
                created_at=when or datetime(2026, 6, 13, tzinfo=UTC),
            )
        )


def test_latest_analysis_none_when_empty(temp_db: str) -> None:
    assert latest_analysis("AAPL") is None


def test_latest_analysis_round_trips(temp_db: str) -> None:
    _store("AAPL", 100.0, "wf-1:AAPL")
    got = latest_analysis("aapl")  # case-insensitive
    assert got is not None and got.symbol == "AAPL"
    assert got.summary.price_now == 100.0


def test_latest_analysis_picks_most_recent(temp_db: str) -> None:
    _store("AAPL", 100.0, "wf-1:AAPL", datetime(2026, 6, 10, tzinfo=UTC))
    _store("AAPL", 200.0, "wf-2:AAPL", datetime(2026, 6, 13, tzinfo=UTC))
    got = latest_analysis("AAPL")
    assert got is not None and got.summary.price_now == 200.0
