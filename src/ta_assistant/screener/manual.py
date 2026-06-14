"""Manually add a ticker to the screener — fetch/validate its bars, score it with the
same pre-screen as the scanner, and return a candidate the user can push to the alpha
pipeline. Returns None if the symbol can't be fetched (so the API can 400)."""

from __future__ import annotations

from datetime import datetime

from ta_assistant.data.bars_repo import load_bars, upsert_bars
from ta_assistant.data.providers import get_daily_history
from ta_assistant.regime import universe as RU
from ta_assistant.screener import universe as SU
from ta_assistant.screener.favour import score_ticker
from ta_assistant.synthesis.schema import ScreenerCandidate, ScreenFactor

_HISTORY = 820


def build_manual_candidate(symbol: str, now: datetime) -> ScreenerCandidate | None:
    sym = symbol.strip().upper()
    if not sym:
        return None
    try:
        df, source = get_daily_history(sym)
    except Exception:  # noqa: BLE001 - unknown/unfetchable symbol -> let the caller 400
        return None
    if len(df) < 50:
        return None
    df = df.iloc[-_HISTORY:] if len(df) > _HISTORY else df
    upsert_bars(df, sym, "D", source)

    spy = load_bars(RU.SPY, "D")
    if len(spy) == 0:  # no scan has run yet — fetch SPY so we can score
        try:
            sdf, ssrc = get_daily_history(RU.SPY)
            spy = sdf.iloc[-_HISTORY:] if len(sdf) > _HISTORY else sdf
            upsert_bars(spy, RU.SPY, "D", ssrc)
        except Exception:  # noqa: BLE001
            spy = df.iloc[0:0]

    score = 0.0
    factors: list[ScreenFactor] = []
    if len(spy) > 0 and len(df) >= 200:
        score, factors, _ = score_ticker(df, spy)
    return ScreenerCandidate(
        symbol=sym,
        sector=SU.sector_of(sym) or "unknown",
        score=round(score, 2),
        factors=factors,
        source="manual",
        generated_at=now,
    )
