"""Central configuration, loaded from environment / .env via pydantic-settings.

All data-provider and LLM keys are Optional with sensible defaults so the
pre-phase durability proof runs on a clean checkout with zero real keys.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Temporal ----
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "ta-default"

    # ---- Domain DB (SQLite) ----
    db_path: str = "./data/ta.db"

    # ---- Data providers (Phase 1; optional now) ----
    alpaca_api_key: str | None = None
    alpaca_api_secret: str | None = None
    alpaca_paper: bool = True
    fred_api_key: str | None = None

    # ---- LLM (OpenAI vision validator/narrator) ----
    # Accepts either OPENAI_API_KEY or OPENAI_KEY from the environment / .env.
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "OPENAI_KEY"),
    )
    # Strong vision + tool-use reasoning model for the chartist (override via OPENAI_MODEL,
    # e.g. gpt-5.4 / gpt-5.2-pro). gpt-4o is far weaker at distinguishing chart patterns.
    openai_model: str = "gpt-5.2"
    openai_model_cheap: str = "gpt-5-mini"
    # When True AND a key is present, the LLM analyst runs; otherwise the
    # deterministic engine runs alone (so a clean checkout still works).
    llm_enabled: bool = True
    # Anthropic (Claude) — the preferred analyst when its key is present. Fast+capable
    # default for the multi-turn vision+tool loop; override to claude-opus-4-8 for depth.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"

    # ---- API service (FastAPI; serves the Next.js frontend) ----
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Comma-separated allowed CORS origins for the frontend dev/prod hosts.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---- Langfuse (LLM observability: token usage + cost) ----
    langfuse_public_key: str | None = Field(
        default=None, validation_alias=AliasChoices("LANGFUSE_PUBLIC_KEY")
    )
    langfuse_secret_key: str | None = Field(
        default=None, validation_alias=AliasChoices("LANGFUSE_SECRET_KEY")
    )
    langfuse_host: str = "http://localhost:3001"

    # ---- Misc ----
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def langfuse_enabled(self) -> bool:
        """True only if BOTH Langfuse keys are configured."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def llm_active(self) -> bool:
        """True only if LLM use is enabled and SOME provider key is configured."""
        return self.llm_enabled and bool(self.anthropic_api_key or self.openai_api_key)

    @property
    def active_provider(self) -> str:
        """Which analyst provider to use: 'anthropic' (preferred) > 'openai' > 'none'."""
        if not self.llm_enabled:
            return "none"
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"
        return "none"


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings."""
    return Settings()
