"""Workflows — PURE orchestration (deterministic, replayed). No I/O here."""

from __future__ import annotations

from ta_assistant.temporal.workflows.analyze_ticker import AnalyzeTickerWorkflow
from ta_assistant.temporal.workflows.candidate_analysis import CandidateAnalysisWorkflow
from ta_assistant.temporal.workflows.crash_demo import CrashDemoWorkflow

ALL_WORKFLOWS = [AnalyzeTickerWorkflow, CandidateAnalysisWorkflow, CrashDemoWorkflow]

__all__ = [
    "ALL_WORKFLOWS",
    "AnalyzeTickerWorkflow",
    "CandidateAnalysisWorkflow",
    "CrashDemoWorkflow",
]
