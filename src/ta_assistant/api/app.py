"""FastAPI app: CORS for the Next.js frontend + the regime/analysis/llm routers.

Run: `uvicorn ta_assistant.api.app:app --host 127.0.0.1 --port 8000` (Makefile `api`).
Heavy work stays in the Temporal workflows/activities; this only serves JSON + triggers.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ta_assistant.api.routers import analysis, health, llm, regime, screener
from ta_assistant.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TA Assistant API",
        version="1.0.0",
        summary="Market Regime + Ticker Analysis for the Next.js frontend.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(regime.router)
    app.include_router(analysis.router)
    app.include_router(llm.router)
    app.include_router(screener.router)
    return app


app = create_app()
