"""Activities — where ALL I/O and non-determinism live (retried, idempotent)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ta_assistant.temporal.activities.analysis import (
    analyze_timeframe,
    build_analysis,
    persist_analysis_result,
    render_charts,
    synthesize,
)
from ta_assistant.temporal.activities.crash_demo import long_running_step
from ta_assistant.temporal.activities.market import compute_indicators, fetch_bars
from ta_assistant.temporal.activities.persist import persist_analysis
from ta_assistant.temporal.activities.regime import (
    build_regime_snapshot,
    fetch_regime_bars,
    persist_regime,
)

ALL_ACTIVITIES: list[Callable[..., Any]] = [
    fetch_bars,
    compute_indicators,
    persist_analysis,
    long_running_step,
    build_analysis,
    analyze_timeframe,
    synthesize,
    render_charts,
    persist_analysis_result,
    fetch_regime_bars,
    build_regime_snapshot,
    persist_regime,
]

__all__ = [
    "ALL_ACTIVITIES",
    "analyze_timeframe",
    "build_analysis",
    "build_regime_snapshot",
    "compute_indicators",
    "fetch_bars",
    "fetch_regime_bars",
    "long_running_step",
    "persist_analysis",
    "persist_analysis_result",
    "persist_regime",
    "render_charts",
    "synthesize",
]
