"""LLM observability endpoint — a small in-app summary + a deep-link to Langfuse.

The rich cost/token dashboards live in the Langfuse UI; this just tells the frontend
whether observability is on and where to open it (and, best-effort, recent totals)."""

from __future__ import annotations

from fastapi import APIRouter

from ta_assistant.config import get_settings

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/usage")
async def llm_usage() -> dict[str, object]:
    s = get_settings()
    return {
        "enabled": s.langfuse_enabled,
        "ui_url": s.langfuse_host,
        "provider": s.active_provider,
        "model": (
            s.anthropic_model
            if s.active_provider == "anthropic"
            else s.openai_model
            if s.active_provider == "openai"
            else None
        ),
    }
