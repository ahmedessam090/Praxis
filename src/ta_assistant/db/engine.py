"""SQLite engine factory with the concurrency-safe PRAGMA recipe.

WAL + busy_timeout is what lets multiple Temporal activities write to one SQLite
file without spurious "database is locked" errors. PRAGMAs are set on *every*
connection via a connect listener.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, event


def make_engine(db_path: str, echo: bool = False) -> Engine:
    engine = create_engine(f"sqlite:///{db_path}", echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()

    return engine
