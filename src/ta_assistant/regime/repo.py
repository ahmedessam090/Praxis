"""Read/write the Market Regime snapshot to SQLite.

The whole snapshot (input chart series + every metric value + the conclusion) is
stored as JSON in one row, so the dashboard redraws entirely from the DB. Writes
are idempotent on a workflow-derived dedup_key (never attempt/now/random).
"""

from __future__ import annotations

from sqlalchemy import select

from ta_assistant.db.models import RegimeSnapshotRow
from ta_assistant.db.session import session_scope
from ta_assistant.synthesis.schema import RegimeSnapshot


def persist_snapshot(snapshot: RegimeSnapshot, dedup_key: str, db_path: str | None = None) -> str:
    """Idempotently store a snapshot; returns the dedup key."""
    with session_scope(db_path) as session:
        if session.get(RegimeSnapshotRow, dedup_key) is None:
            session.add(
                RegimeSnapshotRow(
                    dedup_key=dedup_key,
                    generated_at=snapshot.generated_at,
                    overall_state=snapshot.overall_state.value,
                    payload_json=snapshot.model_dump_json(),
                )
            )
    return dedup_key


def latest_regime(db_path: str | None = None) -> RegimeSnapshot | None:
    """The most recent persisted snapshot (by logical generated_at), or None."""
    with session_scope(db_path) as session:
        row = session.execute(
            select(RegimeSnapshotRow)
            .order_by(RegimeSnapshotRow.generated_at.desc(), RegimeSnapshotRow.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        return RegimeSnapshot.model_validate_json(row.payload_json)
