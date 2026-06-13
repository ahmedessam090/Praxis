"""Read/write OHLCV bars to SQLite (idempotent upsert on the composite PK)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ta_assistant.config import get_settings
from ta_assistant.db.models import Bars
from ta_assistant.db.session import get_engine, session_scope

_UPSERT_COLS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "raw_close",
    "adj_factor",
    "source",
    "is_partial",
]


def _resolve(db_path: str | None) -> str:
    return db_path if db_path is not None else get_settings().db_path


def _opt_float(row: pd.Series, key: str) -> float | None:
    if key in row and pd.notna(row[key]):
        return float(row[key])
    return None


def upsert_bars(
    df: pd.DataFrame, symbol: str, timeframe: str, source: str, db_path: str | None = None
) -> int:
    """Insert/update bars for (symbol, timeframe). Returns the row count written."""
    if df is None or len(df) == 0:
        return 0
    records = [
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "ts": pd.Timestamp(ts).to_pydatetime(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "raw_close": _opt_float(row, "raw_close"),
            "adj_factor": _opt_float(row, "adj_factor"),
            "source": source,
            "is_partial": bool(row["is_partial"]) if "is_partial" in row else False,
        }
        for ts, row in df.iterrows()
    ]
    # Chunk to stay under SQLite's bound-variable limit (all-time history is 10k+ rows).
    chunk = 500
    with session_scope(db_path) as session:
        for start in range(0, len(records), chunk):
            stmt = sqlite_insert(Bars).values(records[start : start + chunk])
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "timeframe", "ts"],
                set_={col: stmt.excluded[col] for col in _UPSERT_COLS},
            )
            session.execute(stmt)
    return len(records)


def max_ts(symbol: str, timeframe: str, db_path: str | None = None) -> datetime | None:
    with session_scope(db_path) as session:
        return session.execute(
            select(Bars.ts)
            .where(Bars.symbol == symbol, Bars.timeframe == timeframe)
            .order_by(Bars.ts.desc())
            .limit(1)
        ).scalar_one_or_none()


def load_bars(symbol: str, timeframe: str, db_path: str | None = None) -> pd.DataFrame:
    """Load bars as a DataFrame indexed by ts (ascending)."""
    engine = get_engine(_resolve(db_path))
    with engine.connect() as conn:
        df = pd.read_sql_query(
            text(
                "SELECT ts, open, high, low, close, volume, is_partial FROM bars "
                "WHERE symbol = :s AND timeframe = :tf ORDER BY ts"
            ),
            conn,
            params={"s": symbol, "tf": timeframe},
            parse_dates=["ts"],
        )
    return df.set_index("ts")
