"""Alembic environment for the SQLite domain store.

URL precedence: a caller-provided ``sqlalchemy.url`` (e.g. set by a test on the
Config) wins; otherwise it falls back to ``Settings.db_path``. ``render_as_batch``
is on so SQLite ALTERs work in future migrations.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from ta_assistant.config import get_settings
from ta_assistant.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the database URL: a caller-provided value wins, else use settings.
_url = config.get_main_option("sqlalchemy.url")
if not _url:
    config.set_main_option("sqlalchemy.url", f"sqlite:///{get_settings().db_path}")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
