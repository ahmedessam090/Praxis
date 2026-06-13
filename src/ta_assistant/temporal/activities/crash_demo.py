"""Crash-recovery demo activity.

Used by the integration test to prove a workflow resumes after the worker is
SIGKILLed. The activity:
  1. touches `phase1.started` so the test knows when to kill the worker,
  2. performs an idempotent side effect guarded by a dedup marker (exactly-once),
  3. heartbeats while sleeping so a dead worker is detected fast (heartbeat_timeout)
     and the activity is re-dispatched to a fresh worker.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from temporalio import activity

_HEARTBEAT_TICKS = 16
_TICK_SECONDS = 0.5


@activity.defn
async def long_running_step(work_dir: str) -> str:
    work = Path(work_dir)
    (work / "phase1.started").touch()

    appended = work / "phase1.appended"
    if not appended.exists():
        with (work / "side_effect.log").open("a") as handle:
            handle.write("did-work\n")
        appended.touch()

    for _ in range(_HEARTBEAT_TICKS):
        activity.heartbeat()
        await asyncio.sleep(_TICK_SECONDS)
    return "completed"
