"""Shared pytest fixtures.

- `temp_db`: a migrated temporary SQLite DB; also repoints app config/session at it.
- `workflow_env`: a Temporal test environment (time-skipping, falling back to a
  local dev server if the time-skipping server can't start, e.g. no Rosetta).
- `free_port`: helper to avoid clashing with the Docker stack's 7233.
"""

from __future__ import annotations

import socket
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Make the shared synthetic-data helpers (tests/patterns/synth.py) importable from any
# test directory (pytest's prepend import mode only adds the collected file's own dir).
sys.path.insert(0, str(Path(__file__).resolve().parent / "patterns"))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_migrations(db_path: str) -> None:
    """Apply Alembic migrations to a specific SQLite file."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def _clear_db_caches() -> None:
    from ta_assistant.config import get_settings
    from ta_assistant.db import session as session_mod

    get_settings.cache_clear()
    session_mod.get_engine.cache_clear()
    session_mod._sessionmaker_for.cache_clear()


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    db_path = str(tmp_path / "ta.db")
    run_migrations(db_path)
    # Point app code (session_scope / get_settings) at the temp DB.
    monkeypatch.setenv("DB_PATH", db_path)
    _clear_db_caches()
    yield db_path
    _clear_db_caches()


@pytest.fixture
async def workflow_env() -> AsyncIterator[object]:
    from temporalio.testing import WorkflowEnvironment

    try:
        env = await WorkflowEnvironment.start_time_skipping()
    except Exception:  # pragma: no cover - environment-dependent (e.g. no Rosetta)
        env = await WorkflowEnvironment.start_local(port=free_port())
    async with env:
        yield env
