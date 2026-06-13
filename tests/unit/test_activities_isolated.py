"""Activities tested in isolation via ActivityEnvironment (no server)."""

from __future__ import annotations

from pathlib import Path

import pytest
from temporalio.testing import ActivityEnvironment

from ta_assistant.temporal.activities import crash_demo
from ta_assistant.temporal.activities.market import compute_indicators, fetch_bars


async def test_fetch_bars_returns_series() -> None:
    bars = await ActivityEnvironment().run(fetch_bars, "AAPL")
    assert isinstance(bars, list)
    assert len(bars) == 6
    assert bars[-1] == 106.0


async def test_compute_indicators_sma() -> None:
    out = await ActivityEnvironment().run(compute_indicators, [10.0, 20.0, 30.0])
    assert out["sma"] == 20.0
    assert out["last"] == 30.0


async def test_long_running_step_heartbeats_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Make the activity fast for the unit test.
    monkeypatch.setattr(crash_demo, "_HEARTBEAT_TICKS", 2)
    monkeypatch.setattr(crash_demo, "_TICK_SECONDS", 0.01)

    beats: list[tuple[object, ...]] = []
    env = ActivityEnvironment()
    env.on_heartbeat = lambda *details: beats.append(details)

    result = await env.run(crash_demo.long_running_step, str(tmp_path))

    assert result == "completed"
    assert (tmp_path / "phase1.started").exists()
    assert (tmp_path / "side_effect.log").read_text().count("did-work") == 1
    assert len(beats) == 2

    # Re-run (simulating a retry/resume): idempotent, no duplicate side effect.
    await env.run(crash_demo.long_running_step, str(tmp_path))
    assert (tmp_path / "side_effect.log").read_text().count("did-work") == 1
