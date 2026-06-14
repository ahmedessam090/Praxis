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
from ta_assistant.temporal.activities.screener import (
    decide_alpha,
    fetch_screen_bars,
    persist_alpha_result,
    persist_candidates,
    persist_refresh_result,
    rejudge_alpha,
    scan_candidates,
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
    fetch_screen_bars,
    scan_candidates,
    persist_candidates,
    decide_alpha,
    persist_alpha_result,
    rejudge_alpha,
    persist_refresh_result,
]

__all__ = [
    "ALL_ACTIVITIES",
    "analyze_timeframe",
    "build_analysis",
    "build_regime_snapshot",
    "compute_indicators",
    "decide_alpha",
    "fetch_bars",
    "fetch_regime_bars",
    "fetch_screen_bars",
    "long_running_step",
    "persist_alpha_result",
    "persist_analysis",
    "persist_analysis_result",
    "persist_candidates",
    "persist_refresh_result",
    "persist_regime",
    "rejudge_alpha",
    "render_charts",
    "scan_candidates",
    "synthesize",
]
