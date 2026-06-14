"""Workflows — PURE orchestration (deterministic, replayed). No I/O here."""

from __future__ import annotations

from ta_assistant.temporal.workflows.alpha import (
    AlphaCandidateWorkflow,
    AlphaRefreshWorkflow,
)
from ta_assistant.temporal.workflows.analyze_ticker import AnalyzeTickerWorkflow
from ta_assistant.temporal.workflows.candidate_analysis import CandidateAnalysisWorkflow
from ta_assistant.temporal.workflows.crash_demo import CrashDemoWorkflow
from ta_assistant.temporal.workflows.market_regime import MarketRegimeWorkflow
from ta_assistant.temporal.workflows.scanner import ScannerWorkflow

ALL_WORKFLOWS = [
    AlphaCandidateWorkflow,
    AlphaRefreshWorkflow,
    AnalyzeTickerWorkflow,
    CandidateAnalysisWorkflow,
    CrashDemoWorkflow,
    MarketRegimeWorkflow,
    ScannerWorkflow,
]

__all__ = [
    "ALL_WORKFLOWS",
    "AlphaCandidateWorkflow",
    "AlphaRefreshWorkflow",
    "AnalyzeTickerWorkflow",
    "CandidateAnalysisWorkflow",
    "CrashDemoWorkflow",
    "MarketRegimeWorkflow",
    "ScannerWorkflow",
]
