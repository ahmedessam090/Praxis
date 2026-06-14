"""Langfuse instrumentation for the LLM calls — token usage + cost.

A thin, defensive wrapper: `record_llm` extracts token usage from an OpenAI/Anthropic
response and emits a Langfuse generation. It is a NO-OP when Langfuse isn't configured,
and it NEVER raises (any SDK/network/API-shape error is swallowed) so observability can
never break the LLM path or its deterministic fallback. The Langfuse SDK is imported
lazily inside the client builder (Temporal-sandbox rule)."""

from __future__ import annotations

import logging
from typing import Any

from ta_assistant.config import get_settings

logger = logging.getLogger(__name__)

_client: Any | None = None


def _make_client() -> Any:
    """Build (and cache) a Langfuse client from settings. Import is deferred (sandbox)."""
    global _client
    if _client is None:
        from langfuse import Langfuse

        s = get_settings()
        _client = Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host,
        )
    return _client


def _extract_usage(resp: Any, provider: str) -> dict[str, int] | None:
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    if provider == "anthropic":
        return {
            "input": int(getattr(u, "input_tokens", 0) or 0),
            "output": int(getattr(u, "output_tokens", 0) or 0),
        }
    return {
        "input": int(getattr(u, "prompt_tokens", 0) or 0),
        "output": int(getattr(u, "completion_tokens", 0) or 0),
    }


def record_llm(
    *,
    name: str,
    provider: str,
    model: str,
    resp: Any,
    input: Any = None,
    output: Any = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a Langfuse generation for one LLM response (cost computed from model+usage).
    No-op without Langfuse keys; swallows all errors."""
    if not get_settings().langfuse_enabled:
        return
    try:
        client = _make_client()
        gen = client.start_observation(
            as_type="generation",
            name=name,
            model=model,
            input=input,
            output=output,
            usage_details=_extract_usage(resp, provider),
            metadata={"provider": provider, **(metadata or {})},
        )
        gen.end()
        client.flush()
    except Exception as exc:  # noqa: BLE001 - observability must never break the LLM path
        logger.debug("langfuse record failed: %s", exc)
