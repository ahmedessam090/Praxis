"""Replay regression: the committed golden history must replay cleanly.

`Replayer` runs the workflow code against a recorded history WITHOUT a server (no
Rosetta, no network). A future change that reorders activities or reads the clock
breaks replay — protecting already-running workflows. Regenerate the golden file
with `scripts/gen_golden_history.py` after an intentional orchestration change.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from temporalio import workflow
from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

from ta_assistant.temporal.workflows.candidate_analysis import CandidateAnalysisWorkflow

HISTORY = Path(__file__).resolve().parent.parent / "histories" / "candidate_v1.json"


async def test_golden_history_replays_deterministically() -> None:
    history = WorkflowHistory.from_json("wf-golden", HISTORY.read_text())
    await Replayer(workflows=[CandidateAnalysisWorkflow]).replay_workflow(
        history, raise_on_replay_failure=True
    )


@workflow.defn(name="CandidateAnalysisWorkflow")
class _IncompatibleWorkflow:
    """Registered under the same name but structurally different -> replay fails."""

    @workflow.run
    async def run(self, symbol: str) -> dict[str, float]:
        return {"unexpected": 1.0}


async def test_incompatible_workflow_fails_replay() -> None:
    history = WorkflowHistory.from_json("wf-golden", HISTORY.read_text())
    # Replayer raises RuntimeError when the workflow code diverges from history.
    with pytest.raises(RuntimeError):
        await Replayer(workflows=[_IncompatibleWorkflow]).replay_workflow(
            history, raise_on_replay_failure=True
        )
