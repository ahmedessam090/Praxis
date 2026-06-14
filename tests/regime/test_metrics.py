"""P1: each regime metric vs hand-built frames engineered to trigger it."""

from __future__ import annotations

import regime_synth as S

from ta_assistant.regime import metrics as M

# --- 1. primary trend (Dow / Minervini MAs) ---


def test_trend_vs_mas_bull() -> None:
    r = M.trend_vs_mas(S.bull_trend())
    assert r.stacked and r.above_200 and r.ma200_rising
    assert r.status == M.BULLISH


def test_trend_vs_mas_bear() -> None:
    r = M.trend_vs_mas(S.bear_trend())
    assert not r.above_200
    assert r.status == M.BEARISH


# --- 2. Weinstein stage ---


def test_weinstein_stage2() -> None:
    assert M.weinstein_stage(S.weekly_stage2()).stage == 2
    assert M.weinstein_stage(S.weekly_stage2()).status == M.BULLISH


def test_weinstein_stage4() -> None:
    assert M.weinstein_stage(S.weekly_stage4()).stage == 4
    assert M.weinstein_stage(S.weekly_stage4()).status == M.BEARISH


def test_weinstein_stage1_and_3() -> None:
    assert M.weinstein_stage(S.weekly_stage1()).stage == 1
    assert M.weinstein_stage(S.weekly_stage3()).stage == 3


# --- 3. Dow confirmation ---


def test_dow_confirms_uptrend() -> None:
    ind, tr = S.confirming_up()
    r = M.dow_confirmation(ind, tr)
    assert r.confirms and r.status == M.BULLISH


def test_dow_non_confirmation() -> None:
    ind, tr = S.divergence()
    r = M.dow_confirmation(ind, tr)
    assert not r.confirms and r.status == M.NEUTRAL


# --- 4. distribution days ---


def test_distribution_heavy_is_bearish() -> None:
    r = M.distribution_days(S.distribution_heavy(count=6))
    assert r.count == 6 and r.status == M.BEARISH
    assert len(r.dates) == 6


def test_distribution_calm_is_bullish() -> None:
    r = M.distribution_days(S.distribution_calm())
    assert r.count == 0 and r.status == M.BULLISH


# --- 5. follow-through day ---


def test_follow_through_day_detected() -> None:
    r = M.follow_through_day(S.ftd_frame())
    assert r.found and r.status == M.BULLISH
    assert r.gain_pct is not None and r.gain_pct >= 0.0125


def test_no_ftd_in_calm_uptrend() -> None:
    # a quiet drift never posts a >=1.25% up day on higher volume off a fresh low
    r = M.follow_through_day(S.distribution_calm())
    assert not r.found


# --- 6. Minervini Power Trend ---


def test_power_trend_on() -> None:
    r = M.power_trend(S.power_trend_on())
    assert r.on and r.status == M.BULLISH
    assert r.low_above_ema21_days >= 10 and r.ema21_above_sma50_days >= 5


def test_power_trend_off_in_downtrend() -> None:
    r = M.power_trend(S.bear_trend())
    assert not r.on and r.status == M.BEARISH


# --- 7. breadth proxies ---


def test_pct_above_ma() -> None:
    r = M.pct_above_ma(S.basket_mostly_above(above=8, below=2))
    assert r.total == 10 and r.above == 8
    assert r.pct == 80.0 and r.status == M.BULLISH


def test_net_new_highs_lows() -> None:
    r = M.net_new_highs_lows(S.basket_bars_mostly_highs(highs=7, lows=2))
    assert r.highs == 7 and r.lows == 2 and r.net == 5
    assert r.status == M.BULLISH


def test_relative_strength_rising() -> None:
    strong = S.make_daily(S.linear(50.0, 0.5, 130))
    weak = S.make_daily([100.0] * 130)
    r = M.relative_strength(strong, weak)
    assert r.rising and r.status == M.BULLISH


# --- 8. single-asset trend (commodities / dollar / VIX) ---


def test_series_trend_rising() -> None:
    r = M.series_trend(S.make_daily(S.linear(60.0, 0.2, 260)))
    assert r.above_200 and r.rising and r.status == M.BULLISH


# --- 9. liquidity cycle (strict) ---


def test_liquidity_expanding() -> None:
    r = M.liquidity_cycle(
        S.liquidity_expanding_frames(),
        hyg="HYG",
        lqd="LQD",
        dxy="DXY",
        software="IGV",
        spy="SPY",
        high_beta="SPHB",
        low_vol="SPLV",
    )
    assert r.state == "expanding" and r.status == M.BULLISH
    assert r.clear_count == 4


def test_liquidity_not_known_when_flat() -> None:
    r = M.liquidity_cycle(
        S.liquidity_flat_frames(),
        hyg="HYG",
        lqd="LQD",
        dxy="DXY",
        software="IGV",
        spy="SPY",
        high_beta="SPHB",
        low_vol="SPLV",
    )
    assert r.state == "not_known" and r.label == "Not Known"
    assert r.status == M.NEUTRAL


def test_liquidity_not_known_when_insufficient_data() -> None:
    frames = {"HYG": S.make_daily([75.0] * 130), "LQD": S.make_daily([110.0] * 130)}
    r = M.liquidity_cycle(
        frames,
        hyg="HYG",
        lqd="LQD",
        dxy="DXY",
        software="IGV",
        spy="SPY",
        high_beta="SPHB",
        low_vol="SPLV",
    )
    assert r.state == "not_known"
