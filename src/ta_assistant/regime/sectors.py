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

# "Rallying too high" (overheated) — the classical-charting standard for an over-extended,
# climactic advance is DISTANCE ABOVE THE MOVING AVERAGE in a confirmed uptrend (Minervini's
# "extended from the 50-day", Weinstein's late-Stage-2 stretch above the rising mean, O'Neil's
# climax top). NOT an oscillator. We flag a genuine leader that has run too far, too fast.
_OVERHEATED_EXT_PCT = 12.0  # >= 12% above its 50-day MA (climactic for a diversified group ETF)
_OVERHEATED_3M = 30.0  # OR >= +30% over ~3 months (a vertical, O'Neil-style climax run)


@dataclass(frozen=True)
class SectorRank:
    sector: str
    etf: str
    rs_status: str  # bullish | neutral | bearish (sector vs SPY)
    rs_pct: float  # % the ratio sits above its own 50-day MA (RS strength)
    trend_status: str  # the sector ETF's own price trend
    trend_pct: float  # ~3-month % change
    score: float  # composite leadership score (higher = stronger leader)
    ext_pct: float = 0.0  # % the ETF price sits above its OWN 50-day MA (extension)
    overheated: bool = False  # rallying too high — extended/climactic; chasing risks the top


def _extension_pct(trend: M.SeriesTrend) -> float:
    """How far (%) the ETF price sits above its own 50-day MA — the classical extension read."""
    if trend.last is None or not trend.sma50:
        return 0.0
    return round((trend.last / trend.sma50 - 1.0) * 100.0, 1)


def _is_overheated(trend: M.SeriesTrend, ext_pct: float) -> bool:
    """A genuine leader (confirmed uptrend: above a rising 200-day MA) that has run too far:
    >= 12% above its 50-day MA, or >= +30% in ~3 months."""
    in_uptrend = trend.above_200 and trend.rising
    stretched = ext_pct >= _OVERHEATED_EXT_PCT or trend.change_pct * 100.0 >= _OVERHEATED_3M
    return bool(in_uptrend and stretched)


def _score(rs: M.RatioRead, trend: M.SeriesTrend) -> float:
    s = 0.0
    s += 1.0 if rs.status == M.BULLISH else (-1.0 if rs.status == M.BEARISH else 0.0)
    s += (rs.pct_above_sma or 0.0) / 5.0  # RS strength vs its MA
    s += 1.0 if rs.rising else 0.0
    s += (trend.change_pct or 0.0) * 4.0  # own momentum
    s += 0.5 if trend.above_200 else -0.5
    return round(s, 4)


def rank_sectors(
    frames: dict[str, pd.DataFrame], etf_map: dict[str, str] | None = None
) -> list[SectorRank]:
    """Rank a set of group ETFs by leadership (RS vs SPY + own trend), best first. Defaults to
    the GICS `SECTOR_ETF` map (used by the screener for stock→sector mapping); the dashboard
    passes the broader `LEADERSHIP_ETF` (GICS + industry/thematic groups) so a rallying leader
    like Semiconductors surfaces by name. Groups whose ETF/SPY data is missing are skipped."""
    spy = frames.get(U.SPY)
    if spy is None or len(spy) == 0:
        return []
    groups = etf_map if etf_map is not None else U.SECTOR_ETF
    ranks: list[SectorRank] = []
    for sector, etf in groups.items():
        df = frames.get(etf)
        if df is None or len(df) < 60:
            continue
        rs = M.relative_strength(df, spy)
        trend = M.series_trend(df)
        ext = _extension_pct(trend)
        ranks.append(
            SectorRank(
                sector=sector,
                etf=etf,
                rs_status=rs.status,
                rs_pct=round(rs.pct_above_sma or 0.0, 2),
                trend_status=trend.status,
                trend_pct=round(trend.change_pct * 100.0, 1),
                score=_score(rs, trend),
                ext_pct=ext,
                overheated=_is_overheated(trend, ext),
            )
        )
    ranks.sort(key=lambda r: r.score, reverse=True)
    return ranks
