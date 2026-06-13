"""Activities — where ALL I/O and non-determinism live (retried, idempotent)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ta_assistant.temporal.activities.analysis import (
    build_analysis,
    persist_analysis_result,
    render_charts,
    validate_patterns,
)
from ta_assistant.temporal.activities.crash_demo import long_running_step
from ta_assistant.temporal.activities.market import compute_indicators, fetch_bars
from ta_assistant.temporal.activities.persist import persist_analysis

ALL_ACTIVITIES: list[Callable[..., Any]] = [
    fetch_bars,
    compute_indicators,
    persist_analysis,
    long_running_step,
    build_analysis,
    render_charts,
    validate_patterns,
    persist_analysis_result,
]

__all__ = [
    "ALL_ACTIVITIES",
    "build_analysis",
    "compute_indicators",
    "fetch_bars",
    "long_running_step",
    "persist_analysis",
    "persist_analysis_result",
    "render_charts",
    "validate_patterns",
]
