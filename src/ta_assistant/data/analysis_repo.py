"""Read persisted TickerAnalysis results from SQLite (for the API to serve without
re-running the workflow). The full TickerAnalysis is stored as JSON in Analysis.payload_json
(dedup_key `{workflow_id}:{symbol}`); we return the most recent per symbol."""

from __future__ import annotations

from sqlalchemy import select

from ta_assistant.db.models import Analysis
from ta_assistant.db.session import session_scope
from ta_assistant.synthesis.schema import TickerAnalysis


def latest_analysis(symbol: str, db_path: str | None = None) -> TickerAnalysis | None:
    """The most recent stored analysis for `symbol` (by created_at), or None."""
    sym = symbol.upper()
    with session_scope(db_path) as session:
        row = session.execute(
            select(Analysis)
            .where(Analysis.symbol == sym)
            .order_by(Analysis.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None or not row.payload_json:
            return None
        return TickerAnalysis.model_validate_json(row.payload_json)
