"""Geometry toolbox: each tool returns correct, JSON-serialisable, data-backed numbers —
and fit_trendline produces a usable rail on CHOPPY lows the strict detector would reject."""

from __future__ import annotations

import json

import pandas as pd
from synth import ascending_triangle_df, ohlcv_from_close, zigzag_closes

from ta_assistant.analyst.tools import ToolContext, build_registry, run_tool


def _ctx(df: pd.DataFrame) -> ToolContext:
    return ToolContext(symbol="T", timeframe="daily", df=df, seeds=[])


def _ts(df: pd.DataFrame, i: int) -> str:
    return pd.Timestamp(df.index[i]).strftime("%Y-%m-%d")


def test_all_tool_results_are_json_serialisable() -> None:
    df = ascending_triangle_df()
    ctx = _ctx(df)
    reg = build_registry()
    # call each tool with minimal valid args; assert no raise + JSON round-trips
    calls = {
        "recent_ohlc": {"n": 10},
        "list_pivots": {"scale": "fine"},
        "list_sr_levels": {},
        "indicator_snapshot": {},
        "engine_candidates": {},
        "risk_reward": {"entry": 100, "stop": 90, "target": 130},
        "measured_move_target": {"breakout": 100, "base": 80, "direction": "up"},
        "breakout_volume_check": {"at_ts": _ts(df, len(df) - 2)},
    }
    for name, args in calls.items():
        out = run_tool(reg, name, args, ctx)
        assert "error" not in out, f"{name} -> {out}"
        json.dumps(out)  # must not raise


def test_fit_trendline_handles_choppy_rising_lows() -> None:
    # Lows that rise overall but dip in the middle (the case ascending_triangle.py rejects
    # via its strict-monotonic guard). The tool must still return a rising, usable rail.
    df = ascending_triangle_df()
    ctx = _ctx(df)
    reg = build_registry()
    pts = [
        {"ts": _ts(df, 10), "price": 80.0},
        {"ts": _ts(df, 25), "price": 78.0},  # <- dip (non-monotonic)
        {"ts": _ts(df, 40), "price": 86.0},
        {"ts": _ts(df, 55), "price": 92.0},
    ]
    out = run_tool(reg, "fit_trendline", {"points": pts}, ctx)
    assert out["rising"] is True  # rising rail despite the choppy dip
    assert out["value_now"] > out["value_at_start"]
    # log fit also yields a rising rail and projects in log space
    out_log = run_tool(reg, "fit_trendline", {"points": pts, "log": True}, ctx)
    assert out_log["space"] == "log" and out_log["rising"] is True


def test_classify_status_validates_levels() -> None:
    df = ascending_triangle_df()  # closes rise to ~115
    ctx = _ctx(df)
    reg = build_registry()
    end_ts = _ts(df, len(df) - 3)

    sane = run_tool(
        reg,
        "classify_status",
        {"breakout": 100, "stop": 92, "target": 115, "region_end_ts": end_ts},
        ctx,
    )
    assert sane["levels_sane"] is True
    assert sane["status"] in ("forming", "confirmed", "triggered", "invalidated")

    bad = run_tool(
        reg,
        "classify_status",
        {"breakout": 100, "stop": -5, "target": 115, "region_end_ts": end_ts},
        ctx,
    )
    assert bad["levels_sane"] is False  # negative stop rejected (anti-hallucination guard)


def test_measured_move_and_risk_reward_math() -> None:
    ctx = _ctx(ascending_triangle_df())
    reg = build_registry()
    mm = run_tool(reg, "measured_move_target", {"breakout": 100, "base": 80}, ctx)
    assert mm["target"] == 120.0 and mm["height"] == 20.0  # linear (additive)
    mm_log = run_tool(reg, "measured_move_target", {"breakout": 100, "base": 80, "log": True}, ctx)
    assert mm_log["space"] == "log" and mm_log["target"] == 125.0  # 100 * (100/80)
    rr = run_tool(reg, "risk_reward", {"entry": 100, "stop": 90, "target": 130}, ctx)
    assert rr["rr_ratio"] == 3.0


def test_list_pivots_returns_alternating_hl() -> None:
    df = ohlcv_from_close(zigzag_closes([100, 70, 100, 70, 110], 12))
    out = run_tool(build_registry(), "list_pivots", {"scale": "medium"}, _ctx(df))
    kinds = {p["kind"] for p in out["pivots"]}
    assert kinds <= {"H", "L"} and out["pivots"]
    assert all({"ts", "price", "kind"} <= p.keys() for p in out["pivots"])


def test_run_tool_unknown_and_errors_are_data_not_exceptions() -> None:
    ctx = _ctx(ascending_triangle_df())
    reg = build_registry()
    assert "error" in run_tool(reg, "does_not_exist", {}, ctx)
    # missing required points -> handled, returned as error data
    assert "error" in run_tool(reg, "fit_trendline", {"points": []}, ctx)
