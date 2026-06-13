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
    openai_model: str = "gpt-4o"  # configurable; override to the latest vision model
    openai_model_cheap: str = "gpt-4o-mini"
    # When True AND a key is present, the OpenAI validator runs; otherwise the
    # deterministic engine runs alone (so a clean checkout still works).
    llm_enabled: bool = True
    anthropic_api_key: str | None = None  # alternate provider (swappable)

    # ---- Misc ----
    log_level: str = "INFO"

    @property
    def llm_active(self) -> bool:
        """True only if LLM use is enabled and an OpenAI key is configured."""
        return self.llm_enabled and bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings."""
    return Settings()
