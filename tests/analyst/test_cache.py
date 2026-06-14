"""Thesis cache: bars-hash stability, content-hash, and round-trip via LlmCache."""

from __future__ import annotations

from synth import ascending_triangle_df, double_bottom_df

from ta_assistant.analyst.cache import bars_hash, cache_get, cache_put, content_hash
from ta_assistant.synthesis.schema import PatternStatus, Timeframe, TimeframeThesis


def test_bars_hash_stable_and_sensitive() -> None:
    df = ascending_triangle_df()
    assert bars_hash(df) == bars_hash(df.copy())  # identical bars -> identical key
    assert bars_hash(df) != bars_hash(double_bottom_df())  # different bars -> different key


def test_content_hash_order_independent() -> None:
    a = content_hash({"symbol": "ERO", "tf": "weekly", "prompt": "v1"})
    b = content_hash({"prompt": "v1", "tf": "weekly", "symbol": "ERO"})
    assert a == b


def test_thesis_round_trip_through_cache(temp_db: str) -> None:
    key = content_hash({"symbol": "ERO", "bars": bars_hash(ascending_triangle_df())})
    assert cache_get(key, TimeframeThesis, db_path=temp_db) is None
    thesis = TimeframeThesis(
        timeframe=Timeframe.WEEKLY,
        pattern_label="ascending triangle",
        status=PatternStatus.FORMING,
        confidence=0.8,
        breakout=33.0,
        target=40.0,
        stop=25.0,
        source="llm",
    )
    cache_put(key, "claude", thesis, db_path=temp_db)
    got = cache_get(key, TimeframeThesis, db_path=temp_db)
    assert got is not None and got.pattern_label == "ascending triangle" and got.target == 40.0
    # idempotent: a second put does not raise or duplicate
    cache_put(key, "claude", thesis, db_path=temp_db)
    assert cache_get(key, TimeframeThesis, db_path=temp_db) is not None
