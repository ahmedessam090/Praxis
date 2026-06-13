"""HEADLINE durability proof: a workflow survives a worker SIGKILL and resumes.

A real worker subprocess starts CrashDemoWorkflow, gets SIGKILLed mid-activity, a
fresh worker takes over, and the workflow completes — SAME run id (resumed, not
restarted) with an EXACTLY-ONCE side effect (the re-dispatched activity is
idempotent). Runs against a local dev server with on-disk persistence.
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import sys
import time
from pathlib import Path

import pytest
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _spawn_worker(
    address: str, task_queue: str, log_path: Path
) -> asyncio.subprocess.Process:
    env = {
        **os.environ,
        "TEMPORAL_ADDRESS": address,
        "TEMPORAL_NAMESPACE": "default",
        "TEMPORAL_TASK_QUEUE": task_queue,
    }
    log = log_path.open("ab")
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "ta_assistant.temporal.worker",
        env=env,
        stdout=log,
        stderr=log,
    )


async def _kill(proc: asyncio.subprocess.Process | None) -> None:
    if proc is not None and proc.returncode is None:
        proc.send_signal(signal.SIGKILL)
        await proc.wait()


async def _wait_for_file(path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"marker {path} never appeared within {timeout}s")


async def test_workflow_survives_worker_crash(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    task_queue = "tq-crash"
    port = _free_port()
    address = f"127.0.0.1:{port}"

    w1: asyncio.subprocess.Process | None = None
    w2: asyncio.subprocess.Process | None = None

    async with await WorkflowEnvironment.start_local(
        port=port,
        dev_server_database_filename=str(tmp_path / "temporal_dev.db"),
    ):
        client = await Client.connect(
            address, namespace="default", data_converter=pydantic_data_converter
        )
        try:
            w1 = await _spawn_worker(address, task_queue, tmp_path / "w1.log")
            handle = await client.start_workflow(
                "CrashDemoWorkflow",
                str(work_dir),
                id="wf-crash-1",
                task_queue=task_queue,
            )
            run_id_started = handle.first_execution_run_id

            # Wait until the activity is genuinely in-flight, then kill the worker.
            await _wait_for_file(work_dir / "phase1.started", timeout=20)
            await _kill(w1)
            w1 = None

            # A fresh worker takes over and the workflow resumes.
            w2 = await _spawn_worker(address, task_queue, tmp_path / "w2.log")
            result = await asyncio.wait_for(handle.result(), timeout=90)
            run_id_finished = handle.result_run_id
        finally:
            await _kill(w1)
            await _kill(w2)

    assert result == "completed"
    # Same run id => the workflow RESUMED from history, it did not restart.
    assert run_id_started and run_id_finished and run_id_started == run_id_finished
    # Exactly-once: the re-dispatched activity did not duplicate its side effect.
    assert (work_dir / "side_effect.log").read_text().count("did-work") == 1
