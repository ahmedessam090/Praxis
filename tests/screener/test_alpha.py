"""Chunk C: the alpha verdict — LLM judgment + deterministic gate fallback + rejudge."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ta_assistant.screener.alpha import decide_alpha_verdict, rejudge_alpha_verdict
from ta_assistant.synthesis.schema import (
    AnalysisSummary,
    Bias,
    IndicatorSnapshot,
    LongPosture,
    PatternStatus,
    RegimeMetric,
    RegimePillar,
    RegimeSnapshot,
    RegimeState,
    TickerAnalysis,
    Timeframe,
    TimeframeThesis,
)

NOW = datetime(2026, 6, 13, tzinfo=UTC)


class _Fake:
    def __init__(self, text: str) -> None:
        self.text = text

    def run_thesis_loop(self, **kw: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def synthesize(self, system: str, user: str) -> str:
        return self.text


def _analysis(
    strong: bool,
    pct50: float | None = None,
    pfh: float | None = None,
    rr: float | None = None,
    weekly_below_200w: bool = False,
    status: PatternStatus = PatternStatus.CONFIRMED,
    close: float = 100.0,
) -> TickerAnalysis:
    ind = IndicatorSnapshot(
        timeframe=Timeframe.DAILY,
        close=close,
        sma50=90.0 if strong else 105.0,
        sma150=80.0 if strong else 110.0,
        sma200=70.0 if strong else 120.0,
        rsi14=60.0,
        atr_pct=2.0,
        pct_from_52w_high=(pfh if pfh is not None else (-3.0 if strong else -45.0)),
        pct_above_sma50=(pct50 if pct50 is not None else (11.0 if strong else -8.0)),
        trend_template_pass=strong,
    )
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
        rr_ratio=(rr if rr is not None else 3.75),
    )
    indicators = [ind]
    if weekly_below_200w:  # weekly close below the 200-week SMA (long-term still repairing)
        indicators.append(
            IndicatorSnapshot(timeframe=Timeframe.WEEKLY, close=100.0, sma200=120.0)
        )
    return TickerAnalysis(
        symbol="NVDA",
        generated_at=NOW,
        timeframes=[Timeframe.DAILY],
        summary=AnalysisSummary(overall_bias=Bias.BULLISH, headline="up", price_now=100.0),
        indicators=indicators,
        theses=[th] if strong else [],
    )


def _regime(risk_on: bool) -> RegimeSnapshot:
    return RegimeSnapshot(
        generated_at=NOW,
        overall_state=RegimeState.CONFIRMED_UPTREND if risk_on else RegimeState.CORRECTION,
        long_posture=LongPosture.SELECTIVE if risk_on else LongPosture.DEFENSIVE,
        pillars=[
            RegimePillar(
                key="sector_leadership",
                name="Sector Leadership",
                metrics=[
                    RegimeMetric(
                        key="sector_technology",
                        label="Technology",
                        value="leading",
                        status=Bias.BULLISH if risk_on else Bias.BEARISH,
                    )
                ],
            )
        ],
    )


def test_deterministic_gate_alpha() -> None:
    v = decide_alpha_verdict(_analysis(True), _regime(True), "technology", _Fake(""))
    assert v.source == "deterministic" and v.is_alpha
    assert v.conviction >= 80 and v.rr == 3.75 and v.entry == 100.0


def test_deterministic_gate_not_alpha() -> None:
    v = decide_alpha_verdict(_analysis(False), _regime(False), "technology", _Fake(""))
    assert v.source == "deterministic" and not v.is_alpha
    assert v.conviction < 50


def test_no_clean_pattern_is_not_alpha_even_when_rallying() -> None:
    # Strong Stage-2 trend + risk-on regime, but the best thesis is "no clean setup" — NOT alpha.
    a = _analysis(True)  # trend-template passes, regime is risk-on
    a.theses = [
        TimeframeThesis(
            timeframe=Timeframe.DAILY,
            pattern_label="no clean setup",
            status=PatternStatus.FORMING,
            direction="bullish",
            confidence=0.0,
        )
    ]
    v = decide_alpha_verdict(a, _regime(True), "technology", _Fake(""))
    assert not v.is_alpha  # a strong uptrend with no clean pattern is not enough
    pat = next(r for r in v.reasons if r.category == "Pattern")
    assert "No clean tradeable pattern" in pat.detail


def test_confirmed_setup_is_awaiting_break_alpha() -> None:
    v = decide_alpha_verdict(_analysis(True), _regime(True), "technology", _Fake(""))
    assert v.is_alpha and v.action_state == "awaiting_break"


def test_forming_pattern_is_not_alpha() -> None:
    # A still-forming structure no longer counts as a tradeable setup.
    v = decide_alpha_verdict(
        _analysis(True, status=PatternStatus.FORMING), _regime(True), "technology", _Fake("")
    )
    assert not v.is_alpha and v.action_state == "not_yet"


def test_extended_setup_stays_alpha_but_flagged() -> None:
    # Triggered, run past the trigger range (close 120, target 130) — still alpha, flagged extended.
    v = decide_alpha_verdict(
        _analysis(True, status=PatternStatus.TRIGGERED, close=120.0),
        _regime(True),
        "technology",
        _Fake(""),
    )
    assert v.is_alpha and v.action_state == "extended"


def test_played_out_setup_is_not_alpha() -> None:
    # Price already at/through the target (130) — the move is done.
    v = decide_alpha_verdict(
        _analysis(True, status=PatternStatus.TRIGGERED, close=130.0),
        _regime(True),
        "technology",
        _Fake(""),
    )
    assert not v.is_alpha and v.action_state == "played_out"


def test_unknown_sector_does_not_block_alpha() -> None:
    # AMKR case: a strong Stage-2 leader in a risk-on regime whose sector is untagged/unknown
    # must NOT be vetoed just because we can't tag its sector.
    v = decide_alpha_verdict(
        _analysis(True), _regime(True), "unknown", _Fake(""), sector_status=None
    )
    assert v.source == "deterministic" and v.is_alpha
    sec = next(r for r in v.reasons if r.category == "Sector")
    assert "not penalized" in sec.detail


def test_leading_sector_is_a_plus_non_leading_is_neutral() -> None:
    # A leading sector raises conviction; a non-leading sector neither blocks nor penalizes.
    leading = decide_alpha_verdict(
        _analysis(True), _regime(True), "technology", _Fake(""), sector_status=Bias.BULLISH
    )
    lagging = decide_alpha_verdict(
        _analysis(True), _regime(True), "energy", _Fake(""), sector_status=Bias.BEARISH
    )
    assert leading.is_alpha and lagging.is_alpha
    assert leading.conviction > lagging.conviction
    sec = next(r for r in lagging.reasons if r.category == "Sector")
    assert sec.status is not Bias.BEARISH  # non-leading is NOT a negative


def test_extension_is_soft_not_a_veto() -> None:
    # >25% above the 50-day MA used to veto alpha outright; now it only lowers conviction.
    v = decide_alpha_verdict(_analysis(True, pct50=32.0), _regime(True), "technology", _Fake(""))
    assert v.is_alpha and v.conviction < 100
    assert any(r.category == "Extension" for r in v.reasons)


def test_risk_reward_is_not_a_gate() -> None:
    # Stops are subjective: a poor R:R must NOT block a genuine Stage-2 leader, and the verdict
    # no longer carries a Risk/Reward reason.
    v = decide_alpha_verdict(_analysis(True, rr=1.1), _regime(True), "technology", _Fake(""))
    assert v.is_alpha
    assert all(r.category != "Risk/Reward" for r in v.reasons)


def test_far_from_highs_is_not_penalized() -> None:
    # Below the highs is NOT a minus: still alpha, and Relative-strength is neutral not bearish.
    v = decide_alpha_verdict(_analysis(True, pfh=-20.0), _regime(True), "technology", _Fake(""))
    assert v.is_alpha
    rs = next(r for r in v.reasons if r.category == "Relative strength")
    assert rs.status is not Bias.BEARISH


def test_near_highs_raises_conviction() -> None:
    at_high = decide_alpha_verdict(
        _analysis(True, pfh=0.0), _regime(True), "technology", _Fake("")
    )
    far = decide_alpha_verdict(_analysis(True, pfh=-20.0), _regime(True), "technology", _Fake(""))
    assert at_high.conviction > far.conviction  # making new highs is a plus


def test_below_200week_is_a_penalty_not_a_veto() -> None:
    with_pen = decide_alpha_verdict(
        _analysis(True, weekly_below_200w=True), _regime(True), "technology", _Fake("")
    )
    without = decide_alpha_verdict(_analysis(True), _regime(True), "technology", _Fake(""))
    assert with_pen.is_alpha  # below the 200-week SMA lowers conviction but does not veto
    assert with_pen.conviction < without.conviction
    assert any(
        r.category == "Long-term trend" and r.status is Bias.BEARISH for r in with_pen.reasons
    )


def test_llm_verdict_parsed() -> None:
    raw = json.dumps(
        {
            "is_alpha": True,
            "conviction": 88,
            "stage": "Stage 2 breakout",
            "regime_alignment": "risk-on, tech leading",
            "entry": 100.0,
            "stop": 92.0,
            "target": 130.0,
            "reasons": [{"category": "Trend", "detail": "Stage 2", "status": "bullish"}],
            "summary": "Leader breaking out; buy over 100, stop 92.",
        }
    )
    v = decide_alpha_verdict(_analysis(True), _regime(True), "technology", _Fake(raw))
    assert v.source == "llm" and v.is_alpha and v.conviction == 88
    assert v.rr == 3.75 and v.reasons[0].status is Bias.BULLISH
    assert "ALPHA EVALUATION" in v.inputs and "technology" in v.inputs  # captured inputs


def test_llm_parse_fail_falls_back() -> None:
    v = decide_alpha_verdict(_analysis(True), _regime(True), "technology", _Fake("no json here"))
    assert v.source == "deterministic" and v.is_alpha


def test_rejudge_downgrade() -> None:
    prior = decide_alpha_verdict(_analysis(True), _regime(True), "technology", _Fake(""))
    raw = json.dumps(
        {
            "is_alpha": False,
            "conviction": 20,
            "stage": "extended",
            "regime_alignment": "weakening",
            "reasons": [{"category": "Extension", "detail": "far above 50d", "status": "bearish"}],
            "summary": "Has run too far and lost RS; no longer alpha.",
        }
    )
    v = rejudge_alpha_verdict(_analysis(True), prior, _regime(True), "technology", _Fake(raw))
    assert not v.is_alpha and v.source == "llm"
