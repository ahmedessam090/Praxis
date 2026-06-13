"""Alembic migrations build the schema, and the app engine enables WAL."""

from __future__ import annotations

import json

import sqlalchemy as sa

from ta_assistant.db.models import Analysis
from ta_assistant.db.session import get_engine, session_scope


def test_migrations_create_expected_tables(temp_db: str) -> None:
    inspector = sa.inspect(get_engine(temp_db))
    tables = set(inspector.get_table_names())
    assert {"workflow_runs", "analyses", "alembic_version"} <= tables


def test_app_engine_enables_wal(temp_db: str) -> None:
    with get_engine(temp_db).connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode;").scalar()
    assert str(mode).lower() == "wal"


def test_orm_roundtrip_on_migrated_schema(temp_db: str) -> None:
    with session_scope(temp_db) as session:
        session.add(Analysis(dedup_key="k1", symbol="AAPL", payload_json=json.dumps({"sma": 1.0})))
    with session_scope(temp_db) as session:
        row = session.get(Analysis, "k1")
        assert row is not None
        assert row.symbol == "AAPL"
        assert json.loads(row.payload_json or "{}")["sma"] == 1.0
