"""P2: pillar aggregation + the deterministic baseline verdict (state/posture)."""

from __future__ import annotations

import pandas as pd
import regime_synth as S

import ta_assistant.regime.universe as U
from ta_assistant.regime.pillars import assess
from ta_assistant.synthesis.schema import Bias, LongPosture, RegimeState


def _now(frames: dict[str, pd.DataFrame]) -> object:
    last = max(f.index[-1] for f in frames.values())
    return (pd.Timestamp(last) + pd.Timedelta(days=3)).to_pydatetime()


def _bull_frames() -> dict[str, pd.DataFrame]:
    f: dict[str, pd.DataFrame] = {}
    for s in (U.SP500, U.NASDAQ, U.DOW_INDUSTRIALS, U.DOW_TRANSPORTS):
        f[s] = S.bull_trend()
    f[U.RSP] = S.make_daily(S.linear(50.0, 0.5, 320))
    f[U.SPY] = S.make_daily(S.linear(400.0, 0.1, 320))
    for sym in U.BREADTH_BASKET[:6]:
        f[sym] = S.make_daily(S.linear(50.0, 0.4, 260))
    f[U.BREADTH_BASKET[6]] = S.make_daily(S.linear(200.0, -0.4, 260))
    return f


def _bear_frames() -> dict[str, pd.DataFrame]:
    f: dict[str, pd.DataFrame] = {}
    for s in (U.SP500, U.NASDAQ, U.DOW_INDUSTRIALS, U.DOW_TRANSPORTS):
        f[s] = S.bear_trend()
    f[U.RSP] = S.make_daily(S.linear(50.0, -0.4, 320))
    f[U.SPY] = S.make_daily(S.linear(400.0, 0.1, 320))
    for sym in U.BREADTH_BASKET[:6]:
        f[sym] = S.make_daily(S.linear(200.0, -0.4, 260))
    f[U.BREADTH_BASKET[6]] = S.make_daily(S.linear(50.0, 0.4, 260))
    return f


def test_bull_market_confirmed_uptrend_aggressive() -> None:
    f = _bull_frames()
    pillars, v = assess(f, _now(f))
    assert v.state is RegimeState.CONFIRMED_UPTREND
    assert v.posture is LongPosture.AGGRESSIVE  # Power Trend on
    assert v.score > 0.4
    pt = next(p for p in pillars if p.key == "primary_trend")
    assert pt.status is Bias.BULLISH
    assert "Confirmed Uptrend" in v.narrative


def test_bear_market_risk_off() -> None:
    f = _bear_frames()
    _pillars, v = assess(f, _now(f))
    assert v.state in (RegimeState.CORRECTION, RegimeState.BEAR)
    assert v.posture in (LongPosture.DEFENSIVE, LongPosture.CASH)
    assert v.score < 0.0


def test_distribution_pressure_downgrades_state() -> None:
    # bullish trend but 6 distribution days on the S&P -> uptrend under pressure
    f = _bull_frames()
    f[U.SP500] = S.distribution_heavy_on_uptrend()
    _pillars, v = assess(f, _now(f))
    assert v.state is RegimeState.UPTREND_UNDER_PRESSURE
    assert v.posture in (LongPosture.SELECTIVE, LongPosture.DEFENSIVE)


def test_five_pillars_always_present() -> None:
    f = _bull_frames()
    pillars, _v = assess(f, _now(f))
    keys = {p.key for p in pillars}
    assert keys == {"primary_trend", "supply_demand", "breadth", "intermarket", "volatility"}


def test_liquidity_metric_surfaced_not_known_without_data() -> None:
    f = _bull_frames()  # no credit/dollar/software frames provided
    pillars, _v = assess(f, _now(f))
    inter = next(p for p in pillars if p.key == "intermarket")
    liq = next(m for m in inter.metrics if m.key == "liquidity_cycle")
    assert liq.value == "Not Known" and liq.status is Bias.NEUTRAL
