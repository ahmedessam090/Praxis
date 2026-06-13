"""Session access for activities: one short transaction per call.

Engines/sessionmakers are cached per resolved db path so tests can target a temp
DB (via the DB_PATH env var) while production uses the configured path.

Never share a session across activities; never use this from workflow code.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ta_assistant.config import get_settings
from ta_assistant.db.engine import make_engine


@lru_cache
def get_engine(db_path: str) -> Engine:
    return make_engine(db_path)


@lru_cache
def _sessionmaker_for(db_path: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(db_path), future=True, expire_on_commit=False)


def _resolve(db_path: str | None) -> str:
    return db_path if db_path is not None else get_settings().db_path


@contextmanager
def session_scope(db_path: str | None = None) -> Iterator[Session]:
    """Open a session, commit on success, roll back on error, always close."""
    session = _sessionmaker_for(_resolve(db_path))()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
