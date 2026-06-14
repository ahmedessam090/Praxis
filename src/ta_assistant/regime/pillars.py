"""Turn the raw metric reads into the 5 dashboard pillars + a deterministic baseline
verdict (state / posture / mood / narrative).

This is the rules-based anchor: it computes every metric's status and a baseline
overall read. The LLM (P3) then integrates the same facts into the final mood, but
this deterministic verdict is always available as the fallback so the tool never goes
dark. Pure (no I/O); `now` is passed in for the weekly Weinstein resample.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from ta_assistant.data.resample import to_weekly
from ta_assistant.regime import metrics as M
from ta_assistant.regime import universe as U
from ta_assistant.synthesis.schema import (
    Bias,
    LongPosture,
    RegimeMetric,
    RegimePillar,
    RegimeState,
)

_SCORE = {Bias.BULLISH: 1.0, Bias.NEUTRAL: 0.0, Bias.BEARISH: -1.0}
_PILLAR_WEIGHTS = {
    "primary_trend": 0.30,
    "supply_demand": 0.25,
    "breadth": 0.20,
    "intermarket": 0.15,
    "volatility": 0.10,
}


@dataclass(frozen=True)
class Verdict:
    state: RegimeState
    posture: LongPosture
    score: float
    mood: str
    narrative: str
    signals: dict[str, str] = field(default_factory=dict)


def _mk(
    key: str,
    label: str,
    status: str,
    value: str,
    detail: str,
    source: str,
    numeric: float | None = None,
) -> RegimeMetric:
    return RegimeMetric(
        key=key,
        label=label,
        value=value,
        status=Bias(status),
        detail=detail,
        source_tag=source,
        numeric=numeric,
    )


def _score_of(metrics: list[RegimeMetric], keys: set[str] | None = None) -> float:
    sel = metrics if keys is None else [m for m in metrics if m.key in keys]
    if not sel:
        return 0.0
    return sum(_SCORE[m.status] for m in sel) / len(sel)


def _status_from_score(s: float) -> Bias:
    return Bias.BULLISH if s > 0.25 else (Bias.BEARISH if s < -0.25 else Bias.NEUTRAL)


def _trend_word(rising: bool) -> str:
    return "▲ rising" if rising else "▼ falling"


# --------------------------------------------------------------------------- pillars


def _primary_trend(frames: dict[str, pd.DataFrame], now: datetime) -> RegimePillar:
    metrics: list[RegimeMetric] = []
    labels = {U.SP500: "S&P 500", U.NASDAQ: "Nasdaq", U.DOW_INDUSTRIALS: "Dow Industrials"}
    for sym, name in labels.items():
        if sym not in frames or len(frames[sym]) == 0:
            continue
        r = M.trend_vs_mas(frames[sym])
        loc = "above" if r.above_200 else "below"
        slope = "rising" if r.ma200_rising else "flat/falling"
        stk = "stacked 50>150>200" if r.stacked else "MAs not stacked"
        metrics.append(
            _mk(
                f"trend_{sym}",
                f"{name} vs 200-day",
                r.status,
                f"{loc} 200-day ({slope})",
                f"{stk}; close {r.close:.0f}.",
                "Dow Theory / Minervini",
                _SCORE[Bias(r.status)],
            )
        )
    if U.SP500 in frames and len(frames[U.SP500]) > 35:
        stage = M.weinstein_stage(to_weekly(frames[U.SP500], now))
        metrics.append(
            _mk(
                "weinstein_stage",
                "Weinstein stage (S&P weekly)",
                stage.status,
                stage.label,
                "Only Stage 2 (advancing above a rising 30-week MA) is a buy environment.",
                "Weinstein",
                float(stage.stage),
            )
        )
    if U.DOW_INDUSTRIALS in frames and U.DOW_TRANSPORTS in frames:
        dow = M.dow_confirmation(frames[U.DOW_INDUSTRIALS], frames[U.DOW_TRANSPORTS])
        metrics.append(
            _mk(
                "dow_confirmation",
                "Dow Theory confirmation",
                dow.status,
                "confirmed" if dow.confirms else "non-confirmation",
                dow.note,
                "Dow Theory",
            )
        )
    score = _score_of(metrics)
    return RegimePillar(
        key="primary_trend",
        name="Primary Trend",
        status=_status_from_score(score),
        score=score,
        summary="The general market's primary trend (Dow Theory + Weinstein stage).",
        metrics=metrics,
    )


def _supply_demand(frames: dict[str, pd.DataFrame]) -> RegimePillar:
    metrics: list[RegimeMetric] = []
    for sym, name in {U.SP500: "S&P 500", U.NASDAQ: "Nasdaq"}.items():
        if sym not in frames or len(frames[sym]) == 0:
            continue
        d = M.distribution_days(frames[sym])
        metrics.append(
            _mk(
                f"distribution_{sym}",
                f"{name} distribution days",
                d.status,
                f"{d.count} in {d.window}d",
                "Institutional selling; 5–6 in ~5 weeks signals an uptrend under pressure.",
                "O'Neil / IBD",
                float(d.count),
            )
        )
    if U.SP500 in frames and len(frames[U.SP500]) > 0:
        ftd = M.follow_through_day(frames[U.SP500])
        ftd_val = (
            f"yes ({ftd.days_since}d ago, +{(ftd.gain_pct or 0) * 100:.1f}%)"
            if ftd.found
            else "none"
        )
        metrics.append(
            _mk(
                "follow_through_day",
                "Follow-through day",
                ftd.status,
                ftd_val,
                "Confirms a new uptrend after a correction (day 4+, >1.25% on higher volume).",
                "O'Neil / IBD",
            )
        )
        pt = M.power_trend(frames[U.SP500])
        metrics.append(
            _mk(
                "power_trend",
                "Minervini Power Trend",
                pt.status,
                "ON" if pt.on else "off",
                f"Low>21-EMA {pt.low_above_ema21_days}d, "
                f"21-EMA>50-SMA {pt.ema21_above_sma50_days}d.",
                "Minervini",
                1.0 if pt.on else 0.0,
            )
        )
    score = _score_of(metrics)
    return RegimePillar(
        key="supply_demand",
        name="Institutional Supply / Demand",
        status=_status_from_score(score),
        score=score,
        summary="Is institutional money accumulating or distributing (O'Neil / Minervini).",
        metrics=metrics,
    )


def _breadth(frames: dict[str, pd.DataFrame]) -> RegimePillar:
    metrics: list[RegimeMetric] = []
    if U.RSP in frames and U.SPY in frames:
        rs = M.relative_strength(frames[U.RSP], frames[U.SPY])
        metrics.append(
            _mk(
                "rsp_spy",
                "Equal-weight vs cap-weight (RSP/SPY)",
                rs.status,
                _trend_word(rs.rising),
                "Rising = the average stock keeps up (broad); falling = a few generals (narrow).",
                "Breadth (proxy)",
            )
        )
    basket = {s: frames[s]["close"] for s in U.BREADTH_BASKET if s in frames}
    if basket:
        for length, key in ((200, "above200"), (50, "above50")):
            b = M.pct_above_ma(basket, length)
            if b.pct is None:
                continue
            metrics.append(
                _mk(
                    f"pct_{key}",
                    f"% of basket > {length}-day MA",
                    b.status,
                    f"{b.pct:.0f}% ({b.above}/{b.total})",
                    ">60% broad participation, <40% washed out (proxy over a liquid basket).",
                    "Breadth (proxy)",
                    b.pct,
                )
            )
        bars = {s: frames[s] for s in U.BREADTH_BASKET if s in frames}
        hl = M.net_new_highs_lows(bars)
        metrics.append(
            _mk(
                "net_new_highs_lows",
                "Net new 52-wk highs − lows",
                hl.status,
                f"{hl.net:+d} ({hl.highs}H / {hl.lows}L)",
                "Expansion of new highs confirms the advance (proxy over a liquid basket).",
                "Breadth (proxy)",
                float(hl.net),
            )
        )
    score = _score_of(metrics)
    return RegimePillar(
        key="breadth",
        name="Market Breadth",
        status=_status_from_score(score),
        score=score,
        summary="How broad the advance is (Edwards & Magee / Murphy) — proxies, labelled.",
        metrics=metrics,
    )


def _pick(frames: dict[str, pd.DataFrame], primary: str, fallback: str | None) -> str | None:
    if primary in frames and len(frames[primary]) > 5:
        return primary
    if fallback and fallback in frames and len(frames[fallback]) > 5:
        return fallback
    return None


def _intermarket(frames: dict[str, pd.DataFrame]) -> RegimePillar:
    metrics: list[RegimeMetric] = []
    score_keys: set[str] = set()

    # --- liquidity cycle (strict) — the headline intermarket read ---
    liq = M.liquidity_cycle(
        frames,
        hyg=U.HIGH_YIELD,
        lqd=U.IG_CREDIT,
        dxy=_pick(frames, U.DXY, "DX=F") or U.DXY,
        software=U.SOFTWARE,
        spy=U.SPY,
        high_beta=U.HIGH_BETA,
        low_vol=U.LOW_VOL,
    )
    sig_txt = ", ".join(f"{k}: {v}" for k, v in liq.signals.items()) or "insufficient data"
    metrics.append(
        _mk(
            "liquidity_cycle",
            "Liquidity cycle",
            liq.status,
            liq.label,
            f"Strict read of credit/dollar/software/risk proxies — {sig_txt}.",
            "Murphy intermarket",
        )
    )
    score_keys.add("liquidity_cycle")

    # --- dollar (DXY): a strong dollar is a headwind for risk ---
    dxy_sym = _pick(frames, U.DXY, "DX=F") or _pick(frames, "DX=F", "UUP")
    if dxy_sym and dxy_sym in frames:
        t = M.series_trend(frames[dxy_sym])
        if t.change_pct > 0.02:
            d_status, d_word = M.BEARISH, "strengthening (headwind)"
        elif t.change_pct < -0.02:
            d_status, d_word = M.BULLISH, "weakening (tailwind)"
        else:
            d_status, d_word = M.NEUTRAL, "flat"
        metrics.append(
            _mk(
                "dxy",
                "US Dollar Index (DXY)",
                d_status,
                f"{t.last:.1f} — {d_word}" if t.last else d_word,
                "Murphy: a rising dollar pressures commodities and risk assets.",
                "Murphy intermarket",
            )
        )
        score_keys.add("dxy")

    # --- risk-on/off leadership ratios ---
    pairs = [
        ("offense_defense", "Discretionary vs Staples (XLY/XLP)", U.DISCRETIONARY, U.STAPLES),
        (
            "transports_utilities",
            "Transports vs Utilities (IYT/XLU)",
            U.TRANSPORTS_ETF,
            U.UTILITIES_ETF,
        ),
        ("credit", "Credit risk appetite (HYG/LQD)", U.HIGH_YIELD, U.IG_CREDIT),
    ]
    for key, label, a, b in pairs:
        if a in frames and b in frames:
            rs = M.relative_strength(frames[a], frames[b])
            metrics.append(
                _mk(
                    key,
                    label,
                    rs.status,
                    _trend_word(rs.rising),
                    "Rising favours risk-on; falling favours risk-off.",
                    "Murphy intermarket",
                )
            )
            score_keys.add(key)

    # --- commodities (tracked per request): copper/gold ratio scores; prices are info ---
    copper = _pick(frames, U.COPPER, U.COMMODITY_ETF[U.COPPER])
    gold = _pick(frames, U.GOLD, U.COMMODITY_ETF[U.GOLD])
    if copper and gold:
        rs = M.relative_strength(frames[copper], frames[gold])
        metrics.append(
            _mk(
                "copper_gold",
                "Copper/Gold (growth vs fear)",
                rs.status,
                _trend_word(rs.rising),
                "Rising = growth/risk-on; falling = defensive/fear.",
                "Murphy intermarket",
            )
        )
        score_keys.add("copper_gold")

    commodity_labels = [
        (U.GOLD, "Gold"),
        (U.SILVER, "Silver"),
        (U.OIL, "Oil (WTI)"),
        (U.COPPER, "Copper"),
    ]
    for sym, name in commodity_labels:
        chosen = _pick(frames, sym, U.COMMODITY_ETF[sym])
        if not chosen:
            continue
        t = M.series_trend(frames[chosen])
        metrics.append(
            _mk(
                f"commodity_{sym}",
                name,
                M.NEUTRAL,  # informational — tracked for context, not a risk vote
                f"{t.last:.2f} ({_trend_word(t.rising)} {t.change_pct * 100:+.1f}% 3m)"
                if t.last
                else "n/a",
                "Commodity complex (Murphy intermarket) — context for inflation/growth.",
                "Murphy intermarket",
                t.last,
            )
        )

    score = _score_of(metrics, score_keys)
    return RegimePillar(
        key="intermarket",
        name="Intermarket & Commodities",
        status=_status_from_score(score),
        score=score,
        summary="Cross-asset risk posture, the liquidity cycle, and the commodity complex.",
        metrics=metrics,
    )


def _volatility(frames: dict[str, pd.DataFrame]) -> RegimePillar:
    metrics: list[RegimeMetric] = []
    if U.VIX in frames and len(frames[U.VIX]) > 0:
        vix = frames[U.VIX]
        last = float(vix["close"].iloc[-1])
        t = M.series_trend(vix, lookback=21)
        if last < 16 and not t.rising:
            status, word = M.BULLISH, "calm"
        elif last > 25 or (last > 20 and t.rising):
            status, word = M.BEARISH, "stressed/rising"
        else:
            status, word = M.NEUTRAL, "moderate"
        metrics.append(
            _mk(
                "vix",
                "Volatility (VIX)",
                status,
                f"{last:.1f} — {word}",
                "Confirmation only: rising VIX into falling prices confirms risk-off.",
                "Volatility (confirmation)",
                last,
            )
        )
    score = _score_of(metrics)
    return RegimePillar(
        key="volatility",
        name="Volatility / Confirmation",
        status=_status_from_score(score),
        score=score,
        summary="VIX level + trend — confirmation, not a primary classical signal.",
        metrics=metrics,
    )


# --------------------------------------------------------------------------- verdict


_MOOD = {
    RegimeState.CONFIRMED_UPTREND: "Risk-on — broad, confirmed uptrend",
    RegimeState.UPTREND_UNDER_PRESSURE: "Risk-on but under distribution — tighten up",
    RegimeState.NEUTRAL: "Mixed / range-bound — no clear edge",
    RegimeState.CORRECTION: "Risk-off — market in correction",
    RegimeState.BEAR: "Risk-off — primary downtrend",
}
_STATE_LABEL = {
    RegimeState.CONFIRMED_UPTREND: "Confirmed Uptrend",
    RegimeState.UPTREND_UNDER_PRESSURE: "Uptrend Under Pressure",
    RegimeState.NEUTRAL: "Neutral / Choppy",
    RegimeState.CORRECTION: "Market in Correction",
    RegimeState.BEAR: "Bear / Stage 4",
}


def state_label(state: RegimeState) -> str:
    return _STATE_LABEL.get(state, state.value)


def _metric(pillar: RegimePillar | None, key: str) -> RegimeMetric | None:
    if pillar is None:
        return None
    return next((m for m in pillar.metrics if m.key == key), None)


def _verdict(pillars: list[RegimePillar]) -> Verdict:
    by_key = {p.key: p for p in pillars}
    score = sum(_PILLAR_WEIGHTS.get(p.key, 0.0) * p.score for p in pillars)
    score = max(-1.0, min(1.0, score))

    pt_m = _metric(by_key.get("primary_trend"), f"trend_{U.SP500}")
    spx_up = pt_m is not None and pt_m.status is Bias.BULLISH
    spx_below = pt_m is not None and "below" in pt_m.value

    dist_m = _metric(by_key.get("supply_demand"), f"distribution_{U.SP500}")
    dist_n = int(dist_m.numeric) if dist_m and dist_m.numeric is not None else 0
    dist_nq = _metric(by_key.get("supply_demand"), f"distribution_{U.NASDAQ}")
    dist_n = max(dist_n, int(dist_nq.numeric) if dist_nq and dist_nq.numeric is not None else 0)
    pt_on = (_metric(by_key.get("supply_demand"), "power_trend") or _mk_dummy()).numeric == 1.0

    breadth_m = _metric(by_key.get("breadth"), "pct_above200")
    breadth_pct = breadth_m.numeric if breadth_m else None
    breadth_ok = breadth_pct is None or breadth_pct >= 50.0

    if spx_up and dist_n < 5 and breadth_ok:
        state = RegimeState.CONFIRMED_UPTREND
    elif spx_up and (dist_n >= 5 or not breadth_ok):
        state = RegimeState.UPTREND_UNDER_PRESSURE
    elif spx_below and score < -0.4:
        state = RegimeState.BEAR
    elif spx_below:
        state = RegimeState.CORRECTION
    else:
        state = RegimeState.NEUTRAL

    posture = {
        RegimeState.CONFIRMED_UPTREND: LongPosture.AGGRESSIVE if pt_on else LongPosture.SELECTIVE,
        RegimeState.UPTREND_UNDER_PRESSURE: (
            LongPosture.DEFENSIVE if dist_n >= 7 else LongPosture.SELECTIVE
        ),
        RegimeState.NEUTRAL: LongPosture.SELECTIVE,
        RegimeState.CORRECTION: LongPosture.DEFENSIVE,
        RegimeState.BEAR: LongPosture.CASH,
    }[state]

    narrative = _deterministic_narrative(state, posture, pillars, dist_n, pt_on, breadth_pct)
    signals = {
        "spx_uptrend": str(spx_up),
        "distribution_days": str(dist_n),
        "power_trend_on": str(pt_on),
        "breadth_pct_above_200": "n/a" if breadth_pct is None else f"{breadth_pct:.0f}",
        "overall_score": f"{score:.2f}",
    }
    return Verdict(state, posture, score, _MOOD[state], narrative, signals)


def _mk_dummy() -> RegimeMetric:
    return _mk("_", "_", M.NEUTRAL, "", "", "")


def _deterministic_narrative(
    state: RegimeState,
    posture: LongPosture,
    pillars: list[RegimePillar],
    dist_n: int,
    pt_on: bool,
    breadth_pct: float | None,
) -> str:
    bits = [f"{_STATE_LABEL[state]}. Suggested long posture: {posture.value.upper()}."]
    by_key = {p.key: p for p in pillars}
    pt = by_key.get("primary_trend")
    if pt is not None:
        bits.append(f"Primary trend reads {pt.status.value} ({pt.score:+.2f}).")
    bits.append(
        f"Distribution days: {dist_n} (5–6 = under pressure); "
        f"Power Trend {'ON' if pt_on else 'off'}."
    )
    if breadth_pct is not None:
        bits.append(f"Breadth: {breadth_pct:.0f}% of the basket above its 200-day MA.")
    inter = by_key.get("intermarket")
    liq = _metric(inter, "liquidity_cycle")
    if liq is not None:
        bits.append(f"Liquidity cycle: {liq.value}.")
    return " ".join(bits)


# --------------------------------------------------------------------------- entry point


def assess(frames: dict[str, pd.DataFrame], now: datetime) -> tuple[list[RegimePillar], Verdict]:
    """Compute the 5 pillars and the deterministic baseline verdict from loaded frames."""
    pillars = [
        _primary_trend(frames, now),
        _supply_demand(frames),
        _breadth(frames),
        _intermarket(frames),
        _volatility(frames),
    ]
    return pillars, _verdict(pillars)
