"""Provider abstraction: deterministic NullAnalyst, factory selection, and the bounded
vision+tool loop driven by scripted fake clients (no network) — incl. validate-and-retry."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
from synth import ascending_triangle_df

from ta_assistant.analyst.provider import (
    AnthropicAnalyst,
    NullAnalyst,
    OpenAIAnalyst,
    deterministic_thesis,
    get_analyst,
    textbookize,
)
from ta_assistant.analyst.tools import ToolContext
from ta_assistant.config import Settings
from ta_assistant.synthesis.schema import (
    DetectedPattern,
    PatternStatus,
    PivotPoint,
    PriceNote,
    ShapeKind,
    Timeframe,
    TimeframeThesis,
)


def _ctx(seeds=None) -> ToolContext:
    df = ascending_triangle_df()
    return ToolContext(symbol="T", timeframe="daily", df=df, seeds=seeds or [])


def _ts(ctx: ToolContext, i: int) -> str:
    return pd.Timestamp(ctx.df.index[i]).strftime("%Y-%m-%d")


def _seed_primary() -> DetectedPattern:
    return DetectedPattern(
        id="p0",
        pattern_type="cup_and_handle",
        timeframe=Timeframe.DAILY,
        status=PatternStatus.CONFIRMED,
        geometry_confidence=0.8,
        confidence=0.8,
        role="primary",
        direction="bullish",
        levels={"breakout": 100.0, "target": 120.0, "stop": 90.0, "pattern_height": 20.0},
        entry=100.0,
        target=120.0,
        stop=90.0,
        rr_ratio=2.0,
        region_start=datetime(2020, 2, 1),
        region_end=datetime(2020, 5, 1),
        pivots=[PivotPoint(idx=5, ts=datetime(2020, 3, 1), price=88.0, kind="L")],
    )


# ----------------------------- fake clients -----------------------------


class _FakeAnthropic:
    """Returns scripted tool_use turns. script = list of [(tool_name, input_dict), ...]."""

    def __init__(self, script):
        self.script = list(script)
        self.messages = self

    def create(self, **_kw):
        turn = self.script.pop(0)
        content = [
            SimpleNamespace(type="tool_use", id=f"t{i}", name=n, input=a)
            for i, (n, a) in enumerate(turn)
        ]
        return SimpleNamespace(content=content, stop_reason="tool_use")


class _FakeOpenAI:
    def __init__(self, script):
        self.script = list(script)
        self.chat = self
        self.completions = self

    def create(self, **_kw):
        turn = self.script.pop(0)
        tcs = [
            SimpleNamespace(
                id=f"t{i}", function=SimpleNamespace(name=n, arguments=json.dumps(a))
            )
            for i, (n, a) in enumerate(turn)
        ]
        msg = SimpleNamespace(content="", tool_calls=tcs)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _sane_submit(ctx: ToolContext) -> dict:
    return {
        "pattern_label": "ascending triangle",
        "status": "forming",
        "direction": "bullish",
        "confidence": 0.82,
        "breakout": 100.0,
        "target": 115.0,
        "stop": 92.0,
        "shapes": [
            {
                "kind": "trendline",
                "points": [
                    {"ts": _ts(ctx, 10), "price": 100.0},
                    {"ts": _ts(ctx, 50), "price": 100.0},
                ],
                "role": "resistance",
            }
        ],
        "price_notes": [{"price": 115.0, "label": "Target 115", "kind": "target"}],
        "rationale": "flat resistance ~100, rising lows",
    }


# ------------------------------- tests -------------------------------


def test_null_analyst_builds_thesis_from_seed() -> None:
    ctx = _ctx([_seed_primary()])
    res = NullAnalyst().run_thesis_loop(
        user_text="x", image_paths=[], tool_ctx=ctx, timeframe=Timeframe.DAILY
    )
    assert res.source == "deterministic"
    assert res.thesis is not None
    assert res.thesis.pattern_label == "cup_and_handle"
    assert any(n.kind == "target" for n in res.thesis.price_notes)


def test_deterministic_thesis_no_seeds() -> None:
    t = deterministic_thesis(Timeframe.WEEKLY, [])
    assert t.pattern_label == "no clean long setup"
    assert t.confidence == 0.0


def test_factory_selection() -> None:
    anthropic = get_analyst(Settings(_env_file=None, anthropic_api_key="a"))
    assert isinstance(anthropic, AnthropicAnalyst)
    assert isinstance(get_analyst(Settings(_env_file=None, OPENAI_API_KEY="o")), OpenAIAnalyst)
    assert isinstance(get_analyst(Settings(_env_file=None)), NullAnalyst)


def test_anthropic_loop_runs_tool_then_submits() -> None:
    ctx = _ctx()
    script = [
        [("list_pivots", {"scale": "fine"})],  # turn 1: a geometry tool
        [(("submit_thesis"), _sane_submit(ctx))],  # turn 2: finalize
    ]
    analyst = AnthropicAnalyst("k", "m", client=_FakeAnthropic(script))
    res = analyst.run_thesis_loop(
        user_text="analyze", image_paths=[], tool_ctx=ctx, timeframe=Timeframe.DAILY
    )
    assert res.source == "llm"
    assert res.thesis is not None
    assert res.thesis.pattern_label == "ascending triangle"
    assert res.thesis.breakout == 100.0
    assert res.thesis.shapes and res.thesis.shapes[0].kind.value == "trendline"
    assert any("list_pivots" in t for t in res.thesis.transcript)


def test_openai_loop_validate_and_retry() -> None:
    ctx = _ctx()
    insane = _sane_submit(ctx) | {"stop": 130.0}  # stop > breakout -> must be bounced
    script = [
        [("submit_thesis", insane)],  # turn 1: rejected
        [("submit_thesis", _sane_submit(ctx))],  # turn 2: accepted after the bounce
    ]
    analyst = OpenAIAnalyst("k", "m", client=_FakeOpenAI(script))
    res = analyst.run_thesis_loop(
        user_text="analyze", image_paths=[], tool_ctx=ctx, timeframe=Timeframe.DAILY
    )
    assert res.source == "llm"
    assert res.thesis is not None and res.thesis.stop == 92.0
    # the transcript shows two submit attempts (the validate-and-retry loop)
    assert sum("submit_thesis" in t for t in res.thesis.transcript) == 2


def _seed_hns() -> DetectedPattern:
    piv = [
        PivotPoint(idx=0, ts=datetime(2024, 1, 1), price=100.0, kind="L"),  # LS
        PivotPoint(idx=1, ts=datetime(2024, 2, 1), price=120.0, kind="H"),
        PivotPoint(idx=2, ts=datetime(2024, 3, 1), price=80.0, kind="L"),  # Head (lowest, central)
        PivotPoint(idx=3, ts=datetime(2024, 4, 1), price=120.0, kind="H"),
        PivotPoint(idx=4, ts=datetime(2024, 5, 1), price=100.0, kind="L"),  # RS
    ]
    return DetectedPattern(
        id="w5",
        pattern_type="head_and_shoulders_bottom",
        timeframe=Timeframe.WEEKLY,
        status=PatternStatus.CONFIRMED,
        geometry_confidence=0.8,
        confidence=0.8,
        role="primary",
        direction="bullish",
        levels={"breakout": 120.0, "target": 160.0, "stop": 75.0, "neckline_slope": 0.0,
                "neckline_intercept": 120.0, "pattern_height": 40.0},
        entry=120.0,
        target=160.0,
        stop=75.0,
        region_start=datetime(2024, 1, 1),
        region_end=datetime(2024, 5, 1),
        region_start_idx=0,
        region_end_idx=4,
        pivots=piv,
    )


def test_textbookize_snaps_hns_to_textbook_order() -> None:
    seed = _seed_hns()
    thesis = TimeframeThesis(
        timeframe=Timeframe.WEEKLY,
        pattern_label="Inverse Head-and-Shoulders (H&S bottom)",
        confidence=0.7,
        breakout=999.0,  # LLM's noisy levels — should be snapped to the seed's
        target=999.0,
        stop=999.0,
        source="llm",
        price_notes=[
            PriceNote(price=160.0, label="t", kind="target"),
            PriceNote(price=160.0, label="dup", kind="target"),  # duplicate -> deduped
        ],
    )
    out = textbookize(thesis, [seed])
    markers = [s for s in out.shapes if s.kind == ShapeKind.MARKER]
    assert [m.label for m in markers] == ["LS", "Head", "RS"]  # textbook order
    head = next(m for m in markers if m.label == "Head")
    assert head.points[0].price == 80.0  # head is the central, lowest trough
    assert out.target == 160.0 and out.entry == 120.0  # snapped to the engine's exact levels
    assert sum(n.kind == "target" for n in out.price_notes) == 1  # tags deduped


def test_textbookize_no_match_just_dedupes_notes() -> None:
    t = TimeframeThesis(
        timeframe=Timeframe.DAILY,
        pattern_label="some exotic structure",
        confidence=0.5,
        entry=100.0,
        breakout=100.0,
        target=120.0,
        stop=90.0,
        source="llm",
        price_notes=[
            PriceNote(price=120.0, label="a", kind="target"),
            PriceNote(price=120.0, label="b", kind="target"),
        ],
    )
    out = textbookize(t, [])  # no seeds to match
    assert sum(n.kind == "target" for n in out.price_notes) == 1


def test_loop_gives_up_after_max_turns() -> None:
    ctx = _ctx()
    insane = _sane_submit(ctx) | {"stop": 130.0}
    analyst = AnthropicAnalyst("k", "m", client=_FakeAnthropic([[("submit_thesis", insane)]] * 5))
    res = analyst.run_thesis_loop(
        user_text="x", image_paths=[], tool_ctx=ctx, timeframe=Timeframe.DAILY, max_turns=3
    )
    assert res.thesis is None
    assert res.source == "incomplete"
