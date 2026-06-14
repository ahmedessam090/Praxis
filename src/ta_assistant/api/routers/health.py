"""Health + config probe."""

from __future__ import annotations

from fastapi import APIRouter

from ta_assistant.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    s = get_settings()
    return {
        "status": "ok",
        "active_provider": s.active_provider,
        "langfuse_enabled": s.langfuse_enabled,
    }
