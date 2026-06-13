"""Workflow sandbox configuration.

The Python SDK re-imports workflow modules into a sandbox on every run/replay to
enforce determinism. We pass through our (deterministic-to-import) activity and
model modules plus pydantic for performance. Heavy, non-deterministic libraries
(pandas, numpy, alpaca, matplotlib, anthropic) are imported ONLY inside activity
functions, never at workflow-module import time, so they never reach the sandbox.
"""

from __future__ import annotations

from temporalio.worker.workflow_sandbox import SandboxRestrictions

SANDBOX_RESTRICTIONS = SandboxRestrictions.default.with_passthrough_modules(
    "ta_assistant.temporal.activities",
    "ta_assistant.temporal.activities.market",
    "ta_assistant.temporal.activities.persist",
    "ta_assistant.temporal.activities.crash_demo",
    "ta_assistant.temporal.activities.analysis",
    "ta_assistant.synthesis.schema",
    "ta_assistant.db.models",
    "pydantic",
)
