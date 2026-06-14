"""Content-hash caching for analyst output, reusing the existing `LlmCache` table.

A thesis is a nondeterministic LLM result, so we cache it keyed by the INPUTS (symbol,
timeframe, a hash of the bars, provider, model, prompt version, seed fingerprint). Reruns
with identical data are then stable and free. The caller caches ONLY successful LLM
results (never deterministic fallbacks / failures), so a transient failure can retry.
"""

from __future__ import annotations

import hashlib
import json

import pandas as pd
from pydantic import BaseModel

from ta_assistant.db.models import LlmCache
from ta_assistant.db.session import session_scope


def bars_hash(df: pd.DataFrame) -> str:
    """Stable hash of a timeframe's OHLCV (+ index). Identical bars -> identical key."""
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    h = pd.util.hash_pandas_object(df[cols].round(4), index=True)
    return hashlib.sha256(h.values.tobytes()).hexdigest()[:32]


def content_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def cache_get[T: BaseModel](key: str, cls: type[T], db_path: str | None = None) -> T | None:
    with session_scope(db_path) as session:
        row = session.get(LlmCache, key)
        return cls.model_validate_json(row.result_json) if row is not None else None


def cache_put(key: str, model: str, obj: BaseModel, db_path: str | None = None) -> None:
    payload = obj.model_dump_json()
    with session_scope(db_path) as session:
        if session.get(LlmCache, key) is None:
            session.add(LlmCache(content_hash=key, model=model, result_json=payload))
