"""Geometry TOOLBOX for the AI analyst.

The deterministic geometry that used to gate-keep pattern detection is exposed here as
LLM-callable tools. The analyst looks at the chart, hypothesises a structure, and calls
these to get EXACT, data-backed numbers (fit a rail through pivots it chose, measure a
move, check breakout volume, validate levels) — so it can name a pattern even when the
lines aren't perfectly clean, without hallucinating the levels.

Every tool speaks TIMESTAMPS ('YYYY-MM-DD') on the public boundary (positional bar
indices are an engine internal) and returns compact JSON-serialisable dicts.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ta_assistant.patterns.context import GeometryContext, build_context
from ta_assistant.patterns.detectors.base import (
    BULLISH,
    PatternCandidate,
    classify,
    classify_bearish,
    sane_levels,
)
from ta_assistant.patterns.levels import cluster_prices, prior_resistance
from ta_assistant.patterns.trendlines import fit_trendline
from ta_assistant.patterns.volume import breakout_volume_ratio, is_drying_up, obv_slope
from ta_assistant.synthesis.notes import snapshot
from ta_assistant.synthesis.schema import DetectedPattern, Timeframe

# (atr_mult, min_pct) per ZigZag scale — coarse = multi-year swings, fine = recent detail.
_SCALES: dict[str, tuple[float, float]] = {
    "coarse": (3.0, 0.03),
    "medium": (2.0, 0.02),
    "fine": (1.4, 0.015),
}


def _r(x: float | None, n: int = 2) -> float | None:
    if x is None or not math.isfinite(x):
        return None
    return round(float(x), n)


@dataclass
class ToolContext:
    """Per-(symbol, timeframe) state the tools operate on. Never serialised."""

    symbol: str
    timeframe: str  # "daily" | "weekly" | "monthly"
    df: pd.DataFrame  # full bars for this timeframe (ts-indexed, ascending)
    seeds: list[DetectedPattern] = field(default_factory=list)
    _geo: dict[str, GeometryContext] = field(default_factory=dict)

    def geo(self, scale: str = "medium") -> GeometryContext:
        if scale not in self._geo:
            mult, mp = _SCALES.get(scale, _SCALES["medium"])
            self._geo[scale] = build_context(self.df, self.timeframe, atr_mult=mult, min_pct=mp)
        return self._geo[scale]

    def pos(self, ts: Any) -> int:
        loc = self.df.index.get_indexer([pd.Timestamp(ts)], method="nearest")
        return int(loc[0]) if len(loc) else len(self.df) - 1

    def ts_at(self, idx: int) -> str:
        i = max(0, min(int(idx), len(self.df) - 1))
        return str(pd.Timestamp(self.df.index[i]).strftime("%Y-%m-%d"))


# ----------------------------- tool implementations -----------------------------


def _recent_ohlc(ctx: ToolContext, n: int = 60, end_ts: str | None = None) -> dict[str, Any]:
    n = max(1, min(int(n), 150))
    end = ctx.pos(end_ts) + 1 if end_ts else len(ctx.df)
    window = ctx.df.iloc[max(0, end - n) : end]
    bars = [
        {
            "ts": pd.Timestamp(ts).strftime("%Y-%m-%d"),
            "o": _r(row.open),
            "h": _r(row.high),
            "l": _r(row.low),
            "c": _r(row.close),
            "v": int(row.volume),
        }
        for ts, row in window.iterrows()
    ]
    return {"bars": bars, "count": len(bars)}


def _list_pivots(
    ctx: ToolContext, scale: str = "medium", lookback_bars: int = 260, limit: int = 24
) -> dict[str, Any]:
    window = ctx.df.iloc[-int(lookback_bars) :] if len(ctx.df) > lookback_bars else ctx.df
    mult, mp = _SCALES.get(scale, _SCALES["medium"])
    geo = build_context(window, ctx.timeframe, atr_mult=mult, min_pct=mp)
    pivots = geo.pivots[-int(limit) :]
    return {
        "scale": scale,
        "last_close": _r(ctx.geo().last_close),
        "pivots": [
            {
                "ts": p.ts.strftime("%Y-%m-%d"),
                "price": _r(p.price),
                "kind": p.kind,
                "provisional": p.provisional,
            }
            for p in pivots
        ],
    }


def _fit_trendline(
    ctx: ToolContext, points: list[dict[str, Any]], log: bool = False
) -> dict[str, Any]:
    if not points or len(points) < 2:
        return {"error": "need >= 2 points (each {ts, price})"}
    xs = [ctx.pos(p["ts"]) for p in points]
    raw = [float(p["price"]) for p in points]
    # Fit in LOG space when log=True so a straight 2-point segment sits on the rising lows
    # on a log-scaled chart (the default chart scale). Use for weekly/monthly, large ranges.
    ys = [math.log(v) for v in raw] if log else raw
    line = fit_trendline(xs, ys)

    def val(x: int) -> float:
        v = line.value_at(x)
        return math.exp(v) if log else v

    last_idx = len(ctx.df) - 1
    start_idx, end_idx = min(xs), max(xs)
    return {
        "space": "log" if log else "linear",
        "value_at_start": _r(val(start_idx)),
        "value_at_end": _r(val(end_idx)),
        "value_now": _r(val(last_idx)),  # project the rail to the last bar (draw to here)
        "start_ts": ctx.ts_at(start_idx),
        "end_now_ts": ctx.ts_at(last_idx),
        "rising": val(end_idx) > val(start_idx),
    }


def _fit_horizontal_level(
    ctx: ToolContext, near_price: float, tol_pct: float = 0.02
) -> dict[str, Any]:
    prices = [p.price for p in ctx.geo("fine").pivots]
    if not prices:
        return {"error": "no pivots"}
    tol = max(float(near_price) * float(tol_pct), 1e-9)
    clusters = cluster_prices(prices, tol)
    best = min(clusters, key=lambda lv: abs(lv[0] - float(near_price)))
    members = [p for p in prices if abs(p - best[0]) <= tol]
    return {"level": _r(best[0]), "touch_count": best[1], "members": [_r(m) for m in members]}


def _list_sr_levels(ctx: ToolContext, max_levels: int = 8) -> dict[str, Any]:
    geo = ctx.geo("medium")
    prices = [p.price for p in geo.pivots]
    last = geo.last_close
    tol = max(0.02 * last, 1e-9)
    levels = cluster_prices(prices, tol)
    resistance = prior_resistance(levels, above=last)[: int(max_levels)]
    support = sorted((lv for lv, _ in levels if lv < last), reverse=True)[: int(max_levels)]
    return {
        "last_close": _r(last),
        "resistance": [_r(x) for x in resistance],
        "support": [_r(x) for x in support],
    }


def _measured_move_target(
    ctx: ToolContext, breakout: float, base: float, direction: str = "up", log: bool = False
) -> dict[str, Any]:
    b, base_f = float(breakout), float(base)
    if log and base_f > 0:
        # log/percentage projection: same RATIO move, not the same dollar move (correct on a
        # log chart). target = breakout * (breakout/base); >breakout for up, <breakout for down.
        return {"space": "log", "ratio": _r(b / base_f, 3), "target": _r(b * b / base_f)}
    height = abs(b - base_f)
    target = b + height if direction == "up" else b - height
    return {"space": "linear", "height": _r(height), "target": _r(target)}


def _risk_reward(ctx: ToolContext, entry: float, stop: float, target: float) -> dict[str, Any]:
    risk = abs(float(entry) - float(stop))
    reward = abs(float(target) - float(entry))
    return {"risk": _r(risk), "reward": _r(reward), "rr_ratio": _r(reward / risk) if risk else None}


def _breakout_volume_check(
    ctx: ToolContext, at_ts: str, lookback: int = 20
) -> dict[str, Any]:
    idx = ctx.pos(at_ts)
    start = max(0, idx - int(lookback))
    return {
        "breakout_volume_ratio": _r(breakout_volume_ratio(ctx.df, idx, int(lookback))),
        "obv_slope": _r(obv_slope(ctx.df, start, idx), 4),
        "volume_drying_up": is_drying_up(ctx.df, start, idx),
    }


def _indicator_snapshot(ctx: ToolContext) -> dict[str, Any]:
    snap = snapshot(ctx.df, Timeframe(ctx.timeframe))
    return {k: (_r(v) if isinstance(v, float) else v) for k, v in snap.model_dump().items()}


def _classify_status(
    ctx: ToolContext,
    breakout: float,
    stop: float,
    target: float,
    region_end_ts: str,
    direction: str = "bullish",
    pattern_height: float | None = None,
) -> dict[str, Any]:
    geo = ctx.geo("medium")
    end_idx = ctx.pos(region_end_ts)
    uses_prov = bool(geo.pivots and geo.pivots[-1].provisional)
    height = (
        float(pattern_height)
        if pattern_height is not None
        else abs(float(target) - float(breakout))
    )
    if direction == BULLISH:
        status, bo_idx = classify(geo, end_idx, float(breakout), float(stop), uses_prov)
    else:
        status, bo_idx = classify_bearish(geo, end_idx, float(breakout), float(stop), uses_prov)
    cand = PatternCandidate(
        pattern_type="adhoc",
        timeframe=ctx.timeframe,
        status=status,
        geometry_confidence=0.5,
        pivots=[],
        levels={
            "breakout": float(breakout),
            "target": float(target),
            "stop": float(stop),
            "pattern_height": height,
        },
        region_start_idx=end_idx,
        region_end_idx=end_idx,
        direction=direction,
    )
    last = geo.last_close
    return {
        "status": status,
        "breakout_ts": ctx.ts_at(bo_idx) if bo_idx is not None else None,
        "levels_sane": sane_levels(cand, last),
        "last_close": _r(last),
        "sane_band": [_r(0.25 * last), _r(3.0 * last)],
    }


def _engine_candidates(ctx: ToolContext) -> dict[str, Any]:
    """The deterministic engine's SUGGESTIONS (seed). The analyst may use, refine, or
    ignore them — they no longer gate the analysis."""
    return {
        "candidates": [
            {
                "type": s.pattern_type,
                "tier": s.tier,  # "core" (tradeable) | "support" (context only)
                "direction": s.direction,
                "status": s.status.value,
                "breakout": _r(s.entry),
                "target": _r(s.target),
                "stop": _r(s.stop),
                "region": [s.region_start.strftime("%Y-%m-%d"), s.region_end.strftime("%Y-%m-%d")],
                "geometry_confidence": _r(s.geometry_confidence),
            }
            for s in ctx.seeds
        ]
    }


# --------------------------------- registry ---------------------------------

_TS = {"type": "string", "description": "a date as 'YYYY-MM-DD'"}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for the input object
    fn: Callable[..., dict[str, Any]]


def build_registry() -> list[Tool]:
    return [
        Tool(
            "recent_ohlc",
            "Get recent OHLCV bars to read exact prices near a region.",
            {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "number of bars (<=150)"},
                    "end_ts": _TS,
                },
            },
            _recent_ohlc,
        ),
        Tool(
            "list_pivots",
            "List swing-high/low pivots at a zigzag scale (coarse|medium|fine). Fine "
            "resolves the recent detail; coarse the multi-year swings.",
            {
                "type": "object",
                "properties": {
                    "scale": {"type": "string", "enum": ["coarse", "medium", "fine"]},
                    "lookback_bars": {"type": "integer"},
                },
            },
            _list_pivots,
        ),
        Tool(
            "fit_trendline",
            "Fit a robust (Theil-Sen) line through the pivots/points you choose — even if "
            "they aren't perfectly aligned — and project it to the last bar. Use for a "
            "resistance/support/neckline rail. Set log=true on weekly/monthly or any wide "
            "range so the rail sits correctly on the LOG-scaled chart.",
            {
                "type": "object",
                "properties": {
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"ts": _TS, "price": {"type": "number"}},
                            "required": ["ts", "price"],
                        },
                    },
                    "log": {"type": "boolean", "description": "fit in log price space"},
                },
                "required": ["points"],
            },
            _fit_trendline,
        ),
        Tool(
            "fit_horizontal_level",
            "Find the strongest horizontal price level (support/resistance cluster) near a "
            "price, with its touch count.",
            {
                "type": "object",
                "properties": {
                    "near_price": {"type": "number"},
                    "tol_pct": {"type": "number"},
                },
                "required": ["near_price"],
            },
            _fit_horizontal_level,
        ),
        Tool(
            "list_sr_levels",
            "List clustered support (below price) and resistance (above price) levels.",
            {"type": "object", "properties": {"max_levels": {"type": "integer"}}},
            _list_sr_levels,
        ),
        Tool(
            "measured_move_target",
            "Project a measured-move target from a breakout level and the pattern's "
            "base/peak (direction 'up' or 'down'). Set log=true for a percentage (log) "
            "projection — the correct measure on a log chart / wide range.",
            {
                "type": "object",
                "properties": {
                    "breakout": {"type": "number"},
                    "base": {"type": "number"},
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "log": {"type": "boolean", "description": "percentage (log) projection"},
                },
                "required": ["breakout", "base"],
            },
            _measured_move_target,
        ),
        Tool(
            "risk_reward",
            "Compute risk, reward, and reward:risk for a proposed entry/stop/target.",
            {
                "type": "object",
                "properties": {
                    "entry": {"type": "number"},
                    "stop": {"type": "number"},
                    "target": {"type": "number"},
                },
                "required": ["entry", "stop", "target"],
            },
            _risk_reward,
        ),
        Tool(
            "breakout_volume_check",
            "Volume confirmation at a bar: breakout volume ratio vs the 20-bar average, "
            "OBV slope, and whether volume is drying up.",
            {
                "type": "object",
                "properties": {"at_ts": _TS, "lookback": {"type": "integer"}},
                "required": ["at_ts"],
            },
            _breakout_volume_check,
        ),
        Tool(
            "indicator_snapshot",
            "Current indicator snapshot: SMA50/150/200, RSI, ATR%, 52w high/low, trend "
            "template, relative volume.",
            {"type": "object", "properties": {}},
            _indicator_snapshot,
        ),
        Tool(
            "classify_status",
            "Validate proposed levels and get the deterministic status (forming/confirmed/"
            "triggered/invalidated). 'levels_sane' must be true for a tradeable thesis.",
            {
                "type": "object",
                "properties": {
                    "breakout": {"type": "number"},
                    "stop": {"type": "number"},
                    "target": {"type": "number"},
                    "region_end_ts": _TS,
                    "direction": {"type": "string", "enum": ["bullish", "bearish"]},
                    "pattern_height": {"type": "number"},
                },
                "required": ["breakout", "stop", "target", "region_end_ts"],
            },
            _classify_status,
        ),
        Tool(
            "engine_candidates",
            "The deterministic engine's suggested patterns (hints only — confirm, refine, "
            "or override them with your own read).",
            {"type": "object", "properties": {}},
            _engine_candidates,
        ),
    ]


def run_tool(
    registry: list[Tool], name: str, args: dict[str, Any], ctx: ToolContext
) -> dict[str, Any]:
    """Dispatch a tool call by name; never raises — errors come back as data the model reads."""
    tool = next((t for t in registry if t.name == name), None)
    if tool is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return tool.fn(ctx, **(args or {}))
    except Exception as exc:  # noqa: BLE001 - surface tool errors back to the model
        return {"error": f"{type(exc).__name__}: {exc}"}
