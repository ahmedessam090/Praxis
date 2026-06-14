"""The favour algorithm: rank sectors (regime), then pick candidate tickers from the
curated universe biased toward the leading sectors (but keeping variety), each passing a
deterministic Minervini-style pre-screen. Pure — operates on already-loaded bars."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import pandas as pd

from ta_assistant.regime import metrics as M
from ta_assistant.regime import universe as RU
from ta_assistant.regime.sectors import rank_sectors
from ta_assistant.screener import universe as SU
from ta_assistant.synthesis.notes import snapshot
from ta_assistant.synthesis.schema import (
    Bias,
    CandidateStatus,
    ScreenerCandidate,
    ScreenFactor,
    Timeframe,
)

_MIN_DOLLAR_VOL = 20e6  # liquidity floor (~$20M/day)
_DEFAULT_N = 30


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def score_ticker(df: pd.DataFrame, spy: pd.DataFrame) -> tuple[float, list[ScreenFactor], bool]:
    """Deterministic pre-screen for one candidate: Minervini trend-template + RS vs SPY +
    proximity to the 52-week high + liquidity. Returns (score, factors, qualifies)."""
    if len(df) < 200:
        return 0.0, [], False
    snap = snapshot(df, Timeframe.DAILY)
    rs = M.relative_strength(df, spy)
    trend = M.series_trend(df)
    adv = snap.avg_dollar_volume_20 or 0.0
    liquid = adv >= _MIN_DOLLAR_VOL
    tt = snap.trend_template_pass is True
    pfh = snap.pct_from_52w_high if snap.pct_from_52w_high is not None else -100.0

    qualifies = liquid and (tt or (trend.above_200 and rs.rising))

    score = 0.0
    score += 35.0 if tt else 0.0
    score += 20.0 if rs.rising else 0.0
    score += _clamp(rs.pct_above_sma or 0.0, -10.0, 20.0)
    score += 10.0 if trend.above_200 else -10.0
    if -20.0 <= pfh <= -1.0:
        score += 15.0  # near the high, not extended
    elif pfh > 0.0:
        score += 5.0 - min(pfh, 10.0)  # at/above high — small bump, penalise if stretched
    elif pfh < -40.0:
        score -= 10.0  # deep below the high

    def _b(ok: bool) -> Bias:
        return Bias.BULLISH if ok else Bias.BEARISH

    factors = [
        ScreenFactor(label="Trend template", value="pass" if tt else "fail", status=_b(tt)),
        ScreenFactor(label="RS vs SPY", value=rs.status, status=Bias(rs.status)),
        ScreenFactor(
            label="From 52w high",
            value=f"{pfh:+.0f}%",
            status=Bias.BULLISH if -20.0 <= pfh <= 0.0 else Bias.NEUTRAL,
        ),
        ScreenFactor(
            label="Liquidity",
            value=f"${adv / 1e6:.0f}M/day",
            status=_b(liquid),
        ),
    ]
    return round(score, 2), factors, qualifies


def _slots(rank_index: int) -> int:
    """How many names to draw from the sector at this leadership rank (favour leaders,
    keep variety so even laggard sectors contribute one)."""
    if rank_index < 3:
        return 5
    if rank_index < 7:
        return 3
    return 1


def pick_candidates(
    frames: dict[str, pd.DataFrame],
    existing: Iterable[str],
    now: datetime,
    n: int = _DEFAULT_N,
) -> list[ScreenerCandidate]:
    """Rank sectors, then pick the top qualifying tickers per sector (budget favouring
    leaders), dedupe vs `existing`, and return the top `n` by composite score."""
    spy = frames.get(RU.SPY)
    if spy is None or len(spy) == 0:
        return []
    seen = {s.upper() for s in existing}
    ranks = rank_sectors(frames)
    out: list[ScreenerCandidate] = []
    n_sectors = max(1, len(ranks))

    for i, r in enumerate(ranks):
        sector_bonus = (n_sectors - i) * 1.5  # leaders lift their candidates
        scored: list[tuple[float, str, list[ScreenFactor]]] = []
        for sym in SU.SECTOR_UNIVERSE.get(r.sector, []):
            if sym in seen or sym not in frames:
                continue
            s, factors, ok = score_ticker(frames[sym], spy)
            if ok:
                scored.append((s + sector_bonus, sym, factors))
        scored.sort(key=lambda t: t[0], reverse=True)
        for total, sym, factors in scored[: _slots(i)]:
            seen.add(sym)
            out.append(
                ScreenerCandidate(
                    symbol=sym,
                    sector=r.sector,
                    score=round(total, 2),
                    status=CandidateStatus.PENDING,
                    factors=factors,
                    source="screen",
                    generated_at=now,
                )
            )

    out.sort(key=lambda c: c.score, reverse=True)
    return out[:n]
