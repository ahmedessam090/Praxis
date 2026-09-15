"""SQLAlchemy 2.0 typed models for the domain state store.

Pre-phase ships a minimal schema that proves the activity -> DB write path and
the idempotency story. Phase 1 adds watchlist / patterns / alerts /
regime_snapshots as new Alembic migrations.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WorkflowRun(Base):
    """Journal of durable work units (seed of future run/alert/pattern tables)."""

    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Analysis(Base):
    """Idempotent analysis results keyed by a stable dedup key.

    Activities can run more than once (retry or post-crash resume), so writes are
    idempotent on `dedup_key` (derived from workflow_id + a logical step — never
    from attempt/now/random).
    """

    __tablename__ = "analyses"

    dedup_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Bars(Base):
    """Cached OHLCV bars. Adjusted O/H/L/C is the geometry source of truth; raw
    close + adj_factor are kept for audit / re-adjustment on new corporate actions.

    Composite PK (symbol, timeframe, ts) gives natural idempotency: re-fetching a
    range upserts in place and never duplicates.
    """

    __tablename__ = "bars"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(2), primary_key=True)  # D | W | M
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column()
    high: Mapped[float] = mapped_column()
    low: Mapped[float] = mapped_column()
    close: Mapped[float] = mapped_column()
    volume: Mapped[float] = mapped_column()
    raw_close: Mapped[float | None] = mapped_column(default=None)
    adj_factor: Mapped[float | None] = mapped_column(default=None)
    source: Mapped[str] = mapped_column(String(16))
    is_partial: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmCache(Base):
    """Content-hash cache of LLM validation results (cost control + replay stability)."""

    __tablename__ = "llm_cache"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(48))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegimeSnapshotRow(Base):
    """A persisted Market Regime read — the full snapshot (input chart series + every
    metric value + the conclusion) in payload_json. Idempotent on a workflow-derived
    dedup_key; the dashboard reads the most-recent row by created_at."""

    __tablename__ = "regime_snapshots"

    dedup_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    overall_state: Mapped[str] = mapped_column(String(48))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScreenerCandidateRow(Base):
    """A scanner hit (symbol-keyed for natural dedup + clear/delete). The full
    ScreenerCandidate is in payload_json; a few columns are queryable."""

    __tablename__ = "screener_candidates"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    sector: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))
    group_name: Mapped[str] = mapped_column(String(64), server_default="", default="", index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScreenerGroupRow(Base):
    """A named scanner group (a bucket of candidates the user creates, or that a rally-screen /
    AI pick fills). Persisted so an empty group survives."""

    __tablename__ = "screener_groups"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), server_default="custom", default="custom")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlphaItemRow(Base):
    """A confirmed alpha opportunity (symbol-keyed). Full AlphaItem (verdict + refs) in
    payload_json; the underlying TickerAnalysis lives in `analyses` (reused by the UI)."""

    __tablename__ = "alpha_items"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    conviction: Mapped[int] = mapped_column(Integer)
    sector: Mapped[str] = mapped_column(String(32))
    analysis_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DowngradedItemRow(Base):
    """A formerly-alpha name that no longer qualifies (symbol-keyed)."""

    __tablename__ = "downgraded_items"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
    downgraded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
