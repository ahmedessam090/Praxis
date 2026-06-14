"""Sector leadership ranking — which GICS sectors are leading the market right now.

Pure: ranks each sector ETF by its relative strength vs SPY + its own trend. Used by BOTH
the dashboard's Sector Leadership pillar AND the Alpha scanner's favour algorithm, so the
scanner literally favours what the dashboard shows is leading. Reuses regime.metrics.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ta_assistant.regime import metrics as M
from ta_assistant.regime import universe as U


@dataclass(frozen=True)
class SectorRank:
    sector: str
    etf: str
    rs_status: str  # bullish | neutral | bearish (sector vs SPY)
    rs_pct: float  # % the ratio sits above its own 50-day MA (RS strength)
    trend_status: str  # the sector ETF's own price trend
    trend_pct: float  # ~3-month % change
    score: float  # composite leadership score (higher = stronger leader)


def _score(rs: M.RatioRead, trend: M.SeriesTrend) -> float:
    s = 0.0
    s += 1.0 if rs.status == M.BULLISH else (-1.0 if rs.status == M.BEARISH else 0.0)
    s += (rs.pct_above_sma or 0.0) / 5.0  # RS strength vs its MA
    s += 1.0 if rs.rising else 0.0
    s += (trend.change_pct or 0.0) * 4.0  # own momentum
    s += 0.5 if trend.above_200 else -0.5
    return round(s, 4)


def rank_sectors(frames: dict[str, pd.DataFrame]) -> list[SectorRank]:
    """Rank the GICS sector ETFs by leadership (RS vs SPY + own trend), best first.
    Sectors whose ETF/SPY data is missing are skipped."""
    spy = frames.get(U.SPY)
    if spy is None or len(spy) == 0:
        return []
    ranks: list[SectorRank] = []
    for sector, etf in U.SECTOR_ETF.items():
        df = frames.get(etf)
        if df is None or len(df) < 60:
            continue
        rs = M.relative_strength(df, spy)
        trend = M.series_trend(df)
        ranks.append(
            SectorRank(
                sector=sector,
                etf=etf,
                rs_status=rs.status,
                rs_pct=round(rs.pct_above_sma or 0.0, 2),
                trend_status=trend.status,
                trend_pct=round(trend.change_pct * 100.0, 1),
                score=_score(rs, trend),
            )
        )
    ranks.sort(key=lambda r: r.score, reverse=True)
    return ranks
