"""Settings load with no real keys (so the durability proof runs clean)."""

from ta_assistant.config import Settings, get_settings


def test_settings_defaults_without_real_keys(monkeypatch):
    for var in (
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET",
        "FRED_API_KEY",
        "ANTHROPIC_API_KEY",
        "TEMPORAL_TASK_QUEUE",
        "DB_PATH",
    ):
        monkeypatch.delenv(var, raising=False)

    # _env_file=None isolates the test from any local .env
    s = Settings(_env_file=None)

    assert s.temporal_address == "localhost:7233"
    assert s.temporal_namespace == "default"
    assert s.temporal_task_queue == "ta-default"
    assert s.db_path == "./data/ta.db"

    # Optional provider/LLM keys default to None.
    assert s.alpaca_api_key is None
    assert s.alpaca_api_secret is None
    assert s.fred_api_key is None
    assert s.anthropic_api_key is None


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("TEMPORAL_TASK_QUEUE", "custom-queue")
    monkeypatch.setenv("DB_PATH", "/tmp/custom.db")
    s = Settings(_env_file=None)
    assert s.temporal_task_queue == "custom-queue"
    assert s.db_path == "/tmp/custom.db"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_llm_active_and_provider_selection():
    # no keys -> inactive, provider none
    s = Settings(_env_file=None, llm_enabled=True)
    assert s.llm_active is False
    assert s.active_provider == "none"

    # anthropic key present -> active, anthropic preferred
    s = Settings(_env_file=None, llm_enabled=True, anthropic_api_key="x")
    assert s.llm_active is True
    assert s.active_provider == "anthropic"

    # only openai key -> active, openai (openai_api_key uses a validation_alias)
    s = Settings(_env_file=None, llm_enabled=True, OPENAI_API_KEY="x")
    assert s.llm_active is True
    assert s.active_provider == "openai"

    # both keys -> anthropic wins
    s = Settings(_env_file=None, llm_enabled=True, anthropic_api_key="a", OPENAI_API_KEY="o")
    assert s.active_provider == "anthropic"

    # disabled -> inactive regardless of keys
    s = Settings(_env_file=None, llm_enabled=False, anthropic_api_key="a")
    assert s.llm_active is False
    assert s.active_provider == "none"
