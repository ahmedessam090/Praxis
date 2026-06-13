"""Temporal client factory.

Uses the pydantic data converter so pydantic models (added in later phases)
serialize cleanly as workflow/activity payloads.
"""

from __future__ import annotations

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from ta_assistant.config import get_settings


async def get_client() -> Client:
    settings = get_settings()
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
