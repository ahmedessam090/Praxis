"""Langfuse instrumentation: records usage when keys are set, no-ops without keys, and
never raises (so observability can't break the LLM path)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import ta_assistant.analyst.observability as obs


class _FakeGen:
    def __init__(self, store: dict[str, Any]) -> None:
        self.store = store

    def end(self) -> None:
        self.store["ended"] = True


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.flushed = 0
        self.last: dict[str, Any] = {}

    def start_observation(self, **kw: Any) -> _FakeGen:
        kw.pop("as_type", None)
        self.calls.append(kw)
        return _FakeGen(self.last)

    def flush(self) -> None:
        self.flushed += 1


def _anthropic_resp() -> Any:
    return SimpleNamespace(usage=SimpleNamespace(input_tokens=120, output_tokens=45))


def _openai_resp() -> Any:
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=200, completion_tokens=60))


@pytest.fixture(autouse=True)
def _reset() -> Any:
    from ta_assistant.config import get_settings

    obs._client = None
    get_settings.cache_clear()
    yield
    obs._client = None
    get_settings.cache_clear()  # don't leak LANGFUSE env into other tests' settings cache


def _enable(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    from ta_assistant.config import get_settings

    get_settings.cache_clear()
    fake = _FakeClient()
    monkeypatch.setattr(obs, "_make_client", lambda: fake)
    return fake


def test_no_op_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    # Force the "Langfuse disabled" path regardless of any LANGFUSE keys in the local .env.
    monkeypatch.setattr(obs, "get_settings", lambda: SimpleNamespace(langfuse_enabled=False))
    called = {"n": 0}
    monkeypatch.setattr(obs, "_make_client", lambda: called.__setitem__("n", called["n"] + 1))
    obs.record_llm(name="x", provider="openai", model="gpt-5.2", resp=_openai_resp())
    assert called["n"] == 0  # never even built a client


def test_records_anthropic_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _enable(monkeypatch)
    obs.record_llm(
        name="regime.mood", provider="anthropic", model="claude-sonnet-4-6",
        resp=_anthropic_resp(), input="digest", output="up",
    )
    assert fake.flushed == 1
    call = fake.calls[0]
    assert call["model"] == "claude-sonnet-4-6"
    assert call["usage_details"] == {"input": 120, "output": 45}
    assert call["metadata"]["provider"] == "anthropic"


def test_records_openai_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _enable(monkeypatch)
    obs.record_llm(name="chartist.turn", provider="openai", model="gpt-5.2", resp=_openai_resp())
    assert fake.calls[0]["usage_details"] == {"input": 200, "output": 60}


def test_never_raises_on_sdk_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)

    def _boom() -> Any:
        raise RuntimeError("langfuse down")

    monkeypatch.setattr(obs, "_make_client", _boom)
    # must not raise
    obs.record_llm(name="x", provider="openai", model="gpt-5.2", resp=_openai_resp())
