"""The per-pattern legitimacy/actionability judge — LLM vet + deterministic floor + demotion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ta_assistant.analyst.pattern_judge import deterministic_judgment, judge_patterns
from ta_assistant.synthesis.schema import (
    AnalysisSummary,
    Bias,
    PatternStatus,
    TickerAnalysis,
    Timeframe,
    TimeframeThesis,
)

NOW = datetime(2026, 6, 14, tzinfo=UTC)


class _Fake:
    def __init__(self, text: str) -> None:
        self.text = text

    def run_thesis_loop(self, **kw: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def synthesize(self, system: str, user: str) -> str:
        return self.text


def _analysis(action_state: str, status: PatternStatus = PatternStatus.CONFIRMED) -> TickerAnalysis:
    th = TimeframeThesis(
        timeframe=Timeframe.DAILY,
        pattern_label="ascending triangle",
        status=status,
        direction="bullish",
        confidence=0.8,
        entry=100.0,
        breakout=100.0,
        target=130.0,
        stop=92.0,
        action_state=action_state,
    )
    return TickerAnalysis(
        symbol="NVDA",
        generated_at=NOW,
        timeframes=[Timeframe.DAILY],
        summary=AnalysisSummary(overall_bias=Bias.BULLISH, headline="up", price_now=105.0),
        theses=[th],
    )


def test_deterministic_judgment_valid_for_live_trigger() -> None:
    a = _analysis("awaiting_break")
    j = deterministic_judgment(a.theses[0], "NVDA")
    assert j.valid and j.source == "deterministic"


def test_deterministic_judgment_invalid_for_not_yet() -> None:
    a = _analysis("not_yet", status=PatternStatus.FORMING)
    j = deterministic_judgment(a.theses[0], "NVDA")
    assert not j.valid


def test_llm_valid_keeps_thesis() -> None:
    a = _analysis("awaiting_break")
    raw = json.dumps({"valid": True, "action_state": "awaiting_break", "reason": "clean rails"})
    out = judge_patterns(a, _Fake(raw))
    assert out and out[0].valid and out[0].source == "llm"
    assert a.theses[0].action_state == "awaiting_break"  # not demoted


def test_llm_invalid_demotes_thesis() -> None:
    a = _analysis("awaiting_break")
    raw = json.dumps({"valid": False, "action_state": "invalid", "reason": "rails not real"})
    out = judge_patterns(a, _Fake(raw))
    assert out and not out[0].valid
    assert a.theses[0].action_state == "invalid"  # demoted so the gate skips it


def test_unparseable_falls_back_to_deterministic() -> None:
    a = _analysis("in_range")
    out = judge_patterns(a, _Fake("no json here"))
    assert out and out[0].source == "deterministic" and out[0].valid


def test_no_bull_thesis_returns_empty() -> None:
    a = _analysis("in_range")
    a.theses = []
    assert judge_patterns(a, _Fake("")) == []
