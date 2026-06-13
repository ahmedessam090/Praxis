"""Shared Temporal literals."""

from __future__ import annotations

# Canonical default task queue. The worker reads Settings.temporal_task_queue
# (which defaults to this); scripts/tests may reference it directly.
TASK_QUEUE = "ta-default"
