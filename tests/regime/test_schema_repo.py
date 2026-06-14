"""P0: regime schema round-trips + the snapshot repo (persist/latest, idempotent).

Uses the `temp_db` fixture, which applies the Alembic migrations — so a passing
persist/load here also proves the `regime_snapshots` migration is correct.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from ta_assistant.db.session import get_engine
from ta_assistant.regime.repo import latest_regime, persist_snapshot
from ta_assistant.synthesis.schema import (
    Bias,
    LongPosture,
    RegimeCandle,
    RegimeChart,
    RegimeMetric,
    RegimePillar,
    RegimePoint,
    RegimeSeries,
    RegimeSnapshot,
    RegimeState,
)


def _sample(generated_at: datetime) -> RegimeSnapshot:
    t0 = datetime(2026, 1, 2, tzinfo=UTC)
    t1 = datetime(2026, 1, 3, tzinfo=UTC)
    return RegimeSnapshot(
        generated_at=generated_at,
        overall_state=RegimeState.CONFIRMED_UPTREND,
        long_posture=LongPosture.AGGRESSIVE,
        mood="Risk-on, broad uptrend",
        score=0.62,
        headline="Confirmed uptrend",
        narrative="Indices above rising 200-day; few distribution days.",
        source="deterministic",
        pillars=[
            RegimePillar(
                key="primary_trend",
                name="Primary Trend",
                status=Bias.BULLISH,
                score=0.8,
                summary="SPX above a rising 200-day MA.",
                metrics=[
                    RegimeMetric(
                        key="spx_vs_200",
                        label="S&P 500 vs 200-day",
                        value="above (rising)",
                        status=Bias.BULLISH,
                        detail="Price > 50 > 150 > 200, 200-day rising.",
                        source_tag="Dow Theory",
                        numeric=1.0,
                    )
                ],
            )
        ],
        charts=[
            RegimeChart(
                key="spx",
                title="S&P 500 — daily",
                pillar_key="primary_trend",
                series=[
                    RegimeSeries(
                        label="SMA50",
                        kind="line",
                        color="#2962ff",
                        points=[RegimePoint(ts=t0, value=100.0), RegimePoint(ts=t1, value=101.5)],
                    ),
                    RegimeSeries(
                        label="price",
                        kind="candle",
                        candles=[
                            RegimeCandle(ts=t0, open=99.0, high=102.0, low=98.5, close=101.0),
                            RegimeCandle(ts=t1, open=101.0, high=103.0, low=100.5, close=102.5),
                        ],
                    ),
                ],
            )
        ],
    )


def test_snapshot_json_round_trip() -> None:
    snap = _sample(datetime(2026, 6, 13, 16, 0, tzinfo=UTC))
    restored = RegimeSnapshot.model_validate_json(snap.model_dump_json())
    assert restored == snap
    assert restored.overall_state is RegimeState.CONFIRMED_UPTREND
    assert restored.pillar("primary_trend") is not None
    assert restored.charts_for("primary_trend")[0].series[1].kind == "candle"


def test_persist_and_latest(temp_db: str) -> None:
    snap = _sample(datetime(2026, 6, 13, 16, 0, tzinfo=UTC))
    persist_snapshot(snap, "wf-regime-1:regime")
    got = latest_regime()
    assert got is not None
    assert got.overall_state is RegimeState.CONFIRMED_UPTREND
    assert got.long_posture is LongPosture.AGGRESSIVE
    assert got.charts and got.charts[0].series[0].points[0].value == 100.0


def test_persist_is_idempotent(temp_db: str) -> None:
    snap = _sample(datetime(2026, 6, 13, 16, 0, tzinfo=UTC))
    persist_snapshot(snap, "wf-regime-1:regime")
    persist_snapshot(snap, "wf-regime-1:regime")  # retry / resume — no duplicate
    with get_engine(temp_db).connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM regime_snapshots")).scalar()
    assert count == 1


def test_latest_picks_most_recent(temp_db: str) -> None:
    older = _sample(datetime(2026, 6, 10, 16, 0, tzinfo=UTC))
    newer = _sample(datetime(2026, 6, 13, 16, 0, tzinfo=UTC))
    newer.mood = "newer"
    persist_snapshot(older, "wf-a:regime")
    persist_snapshot(newer, "wf-b:regime")
    got = latest_regime()
    assert got is not None and got.mood == "newer"
