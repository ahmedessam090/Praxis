"""Bars upsert is idempotent; load + max_ts round-trip (temp DB)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ta_assistant.data.bars_repo import load_bars, max_ts, upsert_bars


def _df() -> pd.DataFrame:
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {
            "open": [1.0, 2.0, 3.0],
            "high": [1.5, 2.5, 3.5],
            "low": [0.5, 1.5, 2.5],
            "close": [1.2, 2.2, 3.2],
            "volume": [100.0, 200.0, 300.0],
            "raw_close": [1.2, 2.2, 3.2],
            "adj_factor": [1.0, 1.0, 1.0],
        },
        index=idx,
    )


def test_upsert_is_idempotent_and_roundtrips(temp_db: str) -> None:
    assert upsert_bars(_df(), "AAPL", "D", "test", db_path=temp_db) == 3
    # Re-upsert the same range -> still 3 rows (PK conflict updates in place).
    upsert_bars(_df(), "AAPL", "D", "test", db_path=temp_db)

    loaded = load_bars("AAPL", "D", db_path=temp_db)
    assert len(loaded) == 3
    assert loaded["close"].iloc[-1] == 3.2
    assert max_ts("AAPL", "D", db_path=temp_db) == datetime(2024, 1, 3)


def test_upsert_updates_changed_values(temp_db: str) -> None:
    upsert_bars(_df(), "AAPL", "D", "test", db_path=temp_db)
    changed = _df()
    changed.loc[changed.index[-1], "close"] = 9.9
    upsert_bars(changed, "AAPL", "D", "test", db_path=temp_db)
    loaded = load_bars("AAPL", "D", db_path=temp_db)
    assert len(loaded) == 3  # no duplicate
    assert loaded["close"].iloc[-1] == 9.9  # updated in place


def test_empty_upsert_is_noop(temp_db: str) -> None:
    assert upsert_bars(pd.DataFrame(), "AAPL", "D", "test", db_path=temp_db) == 0
    assert max_ts("AAPL", "D", db_path=temp_db) is None
