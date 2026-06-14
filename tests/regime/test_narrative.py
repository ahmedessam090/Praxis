"""P3: LLM mood synthesis routing — parse/validate, deterministic fallback, and the
real providers' one-shot `synthesize` against fake SDK clients (no network)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from ta_assistant.analyst.provider import AnthropicAnalyst, NullAnalyst, OpenAIAnalyst
from ta_assistant.regime.narrative import build_digest, synthesize_regime_read
from ta_assistant.regime.pillars import Verdict
from ta_assistant.synthesis.schema import (
    Bias,
    LongPosture,
    RegimeMetric,
    RegimePillar,
    RegimeState,
)


def _pillars() -> list[RegimePillar]:
    return [
        RegimePillar(
            key="primary_trend",
            name="Primary Trend",
            status=Bias.BULLISH,
            score=0.8,
            metrics=[
                RegimeMetric(
                    key="trend",
                    label="S&P 500 vs 200-day",
                    value="above (rising)",
                    status=Bias.BULLISH,
                    detail="stacked",
                    source_tag="Dow Theory",
                )
            ],
        )
    ]


def _verdict() -> Verdict:
    return Verdict(
        RegimeState.CONFIRMED_UPTREND,
        LongPosture.AGGRESSIVE,
        0.6,
        "Risk-on",
        "Deterministic baseline narrative.",
        {"distribution_days": "1"},
    )


class _Fake:
    def __init__(self, text: str) -> None:
        self.text = text
        self.seen: list[tuple[str, str]] = []

    def run_thesis_loop(self, **kw: Any) -> Any:  # pragma: no cover - unused here
        raise NotImplementedError

    def synthesize(self, system: str, user: str) -> str:
        self.seen.append((system, user))
        return self.text


def test_digest_lists_metrics_and_baseline() -> None:
    d = build_digest(_pillars(), _verdict())
    assert "MARKET REGIME" in d
    assert "S&P 500 vs 200-day" in d
    assert "Deterministic baseline verdict" in d
    assert "confirmed_uptrend" in d


def test_llm_read_parsed() -> None:
    fake = _Fake(
        json.dumps(
            {
                "overall_state": "uptrend_under_pressure",
                "long_posture": "selective",
                "mood": "Risk-on but extended",
                "narrative": "Trend up but distribution rising; be selective on breakouts.",
            }
        )
    )
    read = synthesize_regime_read(_pillars(), _verdict(), fake)
    assert read.source == "llm"
    assert read.state is RegimeState.UPTREND_UNDER_PRESSURE
    assert read.posture is LongPosture.SELECTIVE
    assert read.mood == "Risk-on but extended"
    # the digest (with the metric facts) was actually sent to the model
    assert fake.seen and "S&P 500 vs 200-day" in fake.seen[0][1]


def test_llm_read_tolerates_prose_and_label_casing() -> None:
    fake = _Fake(
        'Here is my read:\n{"overall_state": "Confirmed Uptrend", '
        '"long_posture": "Aggressive", "mood": "Risk-on", '
        '"narrative": "Broad, confirmed advance."}\nThanks.'
    )
    read = synthesize_regime_read(_pillars(), _verdict(), fake)
    assert read.source == "llm"
    assert read.state is RegimeState.CONFIRMED_UPTREND
    assert read.posture is LongPosture.AGGRESSIVE


def test_empty_falls_back_to_deterministic() -> None:
    read = synthesize_regime_read(_pillars(), _verdict(), _Fake(""))
    assert read.source == "deterministic"
    assert read.narrative == "Deterministic baseline narrative."
    assert read.state is RegimeState.CONFIRMED_UPTREND


def test_invalid_enum_falls_back() -> None:
    fake = _Fake(json.dumps({"overall_state": "to_the_moon", "long_posture": "yolo",
                             "narrative": "x"}))
    read = synthesize_regime_read(_pillars(), _verdict(), fake)
    assert read.source == "deterministic"


def test_garbage_falls_back() -> None:
    read = synthesize_regime_read(_pillars(), _verdict(), _Fake("not json at all"))
    assert read.source == "deterministic"


def test_null_analyst_synthesize_is_empty() -> None:
    assert NullAnalyst().synthesize("sys", "user") == ""


# --- the real providers' synthesize against fake SDK clients ---


class _FakeAnthropic:
    def __init__(self, text: str | None = "hi", raises: bool = False) -> None:
        self._text, self._raises = text, raises
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw: Any) -> Any:
        if self._raises:
            raise RuntimeError("boom")
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._text)]
        )


class _FakeOpenAI:
    def __init__(self, text: str | None = "hi", raises: bool = False) -> None:
        self._text, self._raises = text, raises
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw: Any) -> Any:
        if self._raises:
            raise RuntimeError("boom")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._text))]
        )


def test_anthropic_synthesize_text() -> None:
    a = AnthropicAnalyst("k", "claude-sonnet-4-6", client=_FakeAnthropic("mood text"))
    assert a.synthesize("sys", "user") == "mood text"


def test_anthropic_synthesize_error_returns_empty() -> None:
    a = AnthropicAnalyst("k", "claude-sonnet-4-6", client=_FakeAnthropic(raises=True))
    assert a.synthesize("sys", "user") == ""


def test_openai_synthesize_text() -> None:
    o = OpenAIAnalyst("k", "gpt-5.2", client=_FakeOpenAI("mood text"))
    assert o.synthesize("sys", "user") == "mood text"


def test_openai_synthesize_error_returns_empty() -> None:
    o = OpenAIAnalyst("k", "gpt-5.2", client=_FakeOpenAI(raises=True))
    assert o.synthesize("sys", "user") == ""
