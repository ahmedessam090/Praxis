"""LLM augmentation for the scanner: given the leading sectors, ask the analyst to propose
additional liquid tickers riding the wave (not already considered). No-op without a key;
proposed tickers are validated later by a real data fetch in the scan activity."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable

from ta_assistant.analyst.prompts import SCAN_AUGMENT_SYSTEM
from ta_assistant.analyst.provider import LLMAnalyst
from ta_assistant.regime.sectors import SectorRank

logger = logging.getLogger(__name__)


def propose_extra(
    sector_ranks: list[SectorRank],
    considered: Iterable[str],
    analyst: LLMAnalyst,
    *,
    top_sectors: int = 4,
    max_total: int = 8,
) -> list[tuple[str, str]]:
    """Return (symbol, sector) pairs the LLM proposes in the top sectors, excluding
    `considered`. Empty on no key / unparseable output."""
    leaders = [r for r in sector_ranks[:top_sectors] if r.rs_status != "bearish"]
    if not leaders:
        return []
    seen = {s.upper() for s in considered}
    user = (
        "Leading sectors (best first): "
        + ", ".join(f"{r.sector} ({r.rs_status})" for r in leaders)
        + ".\nAlready considered (exclude these): "
        + ", ".join(sorted(seen))
        + f".\nSector keys to use: {[r.sector for r in leaders]}."
    )
    try:
        raw = analyst.synthesize(SCAN_AUGMENT_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 - augmentation must never break the scan
        logger.debug("scan augment failed: %s", exc)
        return []
    if not raw or "{" not in raw or "}" not in raw:
        return []
    try:
        data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    valid_sectors = {r.sector for r in leaders}
    out: list[tuple[str, str]] = []
    for sector, names in data.items():
        if sector not in valid_sectors or not isinstance(names, list):
            continue
        for raw_sym in names[:4]:
            sym = str(raw_sym).strip().upper()
            if sym and sym.isascii() and sym not in seen and 1 <= len(sym) <= 6:
                seen.add(sym)
                out.append((sym, sector))
    return out[:max_total]
