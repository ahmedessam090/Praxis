"""Deterministic price-levels + textbook chart-gap detection for an alpha name.

Pure functions over a daily OHLCV DataFrame (no DB access). They produce the
``KeyLevel`` / ``GapNote`` records attached to an ``AlphaItem`` when a candidate
becomes ALPHA. Every function is defensive: short or empty input returns ``[]``,
never raises.

The gap classification follows the classical chartist taxonomy (Edwards &
Magee, Murphy):

* **common** gaps are small and occur inside congestion; they fill quickly and
  "add nothing" — we suppress them entirely.
* **breakaway** gaps punch out of a base/consolidation at the *start* of a move,
  usually on heavy volume, and tend to stay unfilled — significant support /
  resistance.
* **runaway** (measuring / continuation) gaps occur *mid-trend*, confirming
  strength on solid volume, typically unfilled.
* **exhaustion** gaps appear near the *end* of an extended move (price already
  stretched well past the ~50-bar MA), often on climactic volume, and usually
  fill soon after — a caution flag.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ta_assistant.synthesis.schema import GapNote, KeyLevel

# --- tunables -----------------------------------------------------------------

_WEEKS_52 = 252  # trading days in ~52 weeks
_PIVOT_K = 8  # ±bars defining a swing pivot
_CLUSTER_PCT = 1.5  # merge levels within this % of each other
_ATH_NEAR_PCT = 8.0  # only surface the all-time high when price is within this %

_VOL_AVG_BARS = 50  # trailing window for the average-volume baseline
_MA_BARS = 50  # the ~50-bar MA used to judge a gap's position in a move
_COMMON_GAP_PCT = 1.0  # gaps smaller than this are "common" (suppressed)
_TIGHT_RANGE_PCT = 8.0  # prior-range width (% of price) below which it's a base
_STRETCHED_PCT = 12.0  # % above the ~50-bar MA that counts as "extended"
_HEAVY_VOL = 1.5  # volume ratio that counts as a heavy / climactic day


# --- shared helpers -----------------------------------------------------------


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop a trailing partial bar and any rows missing OHLC; keep ascending order."""
    if df is None or len(df) == 0:
        return df.iloc[0:0] if df is not None else pd.DataFrame()
    out = df
    if "is_partial" in out.columns and len(out) > 0 and bool(out["is_partial"].iloc[-1]):
        out = out.iloc[:-1]
    cols = [c for c in ("open", "high", "low", "close") if c in out.columns]
    if cols:
        out = out.dropna(subset=cols)
    return out


def _last_close(df: pd.DataFrame) -> float | None:
    if len(df) == 0 or "close" not in df.columns:
        return None
    return float(df["close"].iloc[-1])


def _signed_pct(price: float, ref: float) -> float:
    """Signed % of ``price`` relative to the current ``ref`` (+ above, - below)."""
    if ref == 0:
        return 0.0
    return round((price - ref) / ref * 100.0, 1)


def _pivot_high_idx(highs: np.ndarray, k: int) -> list[int]:
    """Indices i where high[i] is the max within [i-k, i+k] (a swing-high pivot)."""
    n = len(highs)
    out: list[int] = []
    for i in range(k, n - k):
        window = highs[i - k : i + k + 1]
        if highs[i] >= window.max():
            out.append(i)
    return out


def _pivot_low_idx(lows: np.ndarray, k: int) -> list[int]:
    """Indices i where low[i] is the min within [i-k, i+k] (a swing-low pivot)."""
    n = len(lows)
    out: list[int] = []
    for i in range(k, n - k):
        window = lows[i - k : i + k + 1]
        if lows[i] <= window.min():
            out.append(i)
    return out


def _cluster(prices: list[float], pct: float) -> list[float]:
    """Collapse near-duplicate price levels (within ``pct`` of each other) to one."""
    kept: list[float] = []
    for p in prices:
        if all(abs(p - q) / q * 100.0 > pct for q in kept if q != 0):
            kept.append(p)
    return kept


# --- key levels ---------------------------------------------------------------


def key_levels(
    df: pd.DataFrame,
    current_price: float | None = None,
    *,
    max_levels: int = 5,
) -> list[KeyLevel]:
    """Key price levels worth watching for a name: the 52-week high, the all-time
    high (only when price is near it), prior swing-high resistance above price, and
    the nearest swing-low support below price. Nearest-to-price first, capped at
    ``max_levels``.
    """
    data = _clean(df)
    # Need enough bars for a swing pivot (±k) to be meaningful; a handful of bars
    # has no real 52w high / support structure, so degrade gracefully to [].
    if len(data) < 2 * _PIVOT_K + 1:
        return []
    price = current_price if current_price is not None else _last_close(data)
    if price is None or price <= 0:
        return []

    highs = data["high"].to_numpy(dtype=float)
    lows = data["low"].to_numpy(dtype=float)

    above: list[KeyLevel] = []
    below: list[KeyLevel] = []

    # 52-week high (resistance only while price trades below it).
    window_52 = highs[-_WEEKS_52:] if len(highs) >= _WEEKS_52 else highs
    high_52 = float(window_52.max())
    if price < high_52:
        above.append(
            KeyLevel(
                price=round(high_52, 2),
                kind="52w_high",
                label="52-week high",
                distance_pct=_signed_pct(high_52, price),
            )
        )

    # All-time high — only when within ~8% (otherwise it's not "to watch" yet), and
    # skip if it's essentially the same level as the 52-week high (avoid duplicates).
    ath = float(highs.max())
    near_ath = price >= ath * (1.0 - _ATH_NEAR_PCT / 100.0)
    same_as_52 = abs(ath - high_52) / ath * 100.0 <= _CLUSTER_PCT if ath else True
    if near_ath and not same_as_52:
        bucket = above if price < ath else below
        bucket.append(
            KeyLevel(
                price=round(ath, 2),
                kind="all_time_high",
                label="all-time high",
                distance_pct=_signed_pct(ath, price),
            )
        )

    # Prior swing-high resistance ABOVE price (clustered, nearest first).
    pivot_highs = sorted(
        {round(float(highs[i]), 4) for i in _pivot_high_idx(highs, _PIVOT_K)}
    )
    res_above = [p for p in pivot_highs if p > price * (1.0 + _CLUSTER_PCT / 100.0)]
    taken = {lvl.price for lvl in above}
    for p in _cluster(sorted(res_above), _CLUSTER_PCT):
        if any(abs(p - t) / t * 100.0 <= _CLUSTER_PCT for t in taken if t):
            continue  # already covered by the 52w / ATH level
        above.append(
            KeyLevel(
                price=round(p, 2),
                kind="resistance",
                label="prior swing-high resistance",
                distance_pct=_signed_pct(p, price),
            )
        )

    # Nearest significant swing-low support BELOW price (1, at most 2).
    pivot_lows = sorted(
        {round(float(lows[i]), 4) for i in _pivot_low_idx(lows, _PIVOT_K)},
        reverse=True,
    )
    supports = [p for p in pivot_lows if p < price * (1.0 - _CLUSTER_PCT / 100.0)]
    for p in _cluster(supports, _CLUSTER_PCT)[:2]:
        below.append(
            KeyLevel(
                price=round(p, 2),
                kind="support",
                label="recent support / base floor",
                distance_pct=_signed_pct(p, price),
            )
        )

    # Order each side by distance from price, then interleave nearest-first overall.
    above.sort(key=lambda lvl: abs(lvl.distance_pct))
    below.sort(key=lambda lvl: abs(lvl.distance_pct))
    ordered = sorted(above + below, key=lambda lvl: abs(lvl.distance_pct))
    return ordered[:max_levels]


# --- gaps ---------------------------------------------------------------------


def detect_gaps(
    df: pd.DataFrame,
    *,
    lookback: int = 150,
    max_notes: int = 4,
) -> list[GapNote]:
    """Find textbook (non-common) price gaps in the last ``lookback`` bars and
    classify each as breakaway / runaway / exhaustion. Common gaps (small and/or
    in-congestion) are suppressed. Most-recent first, capped at ``max_notes``.
    """
    data = _clean(df)
    if len(data) < _PIVOT_K + 2:
        return []

    highs = data["high"].to_numpy(dtype=float)
    lows = data["low"].to_numpy(dtype=float)
    closes = data["close"].to_numpy(dtype=float)
    has_vol = "volume" in data.columns
    vols = data["volume"].to_numpy(dtype=float) if has_vol else np.zeros(len(data))
    index = list(data.index)
    n = len(data)

    ma = (
        pd.Series(closes).rolling(_MA_BARS, min_periods=1).mean().to_numpy(dtype=float)
    )

    start = max(1, n - lookback)
    notes: list[GapNote] = []

    for i in range(start, n):
        up = lows[i] > highs[i - 1]
        down = highs[i] < lows[i - 1]
        if not (up or down):
            continue

        if up:
            lower, upper, edge, direction = highs[i - 1], lows[i], highs[i - 1], "up"
        else:
            lower, upper, edge, direction = highs[i], lows[i - 1], lows[i - 1], "down"
        if edge <= 0:
            continue
        gap_pct = round((upper - lower) / edge * 100.0, 2)

        vol_ratio = _volume_ratio(vols, i) if has_vol else None
        filled = _is_filled(highs, lows, i, lower, upper, direction)

        if _is_common(gap_pct, highs, lows, i, filled):
            continue

        kind, note = _classify(
            direction=direction,
            gap_pct=gap_pct,
            lower=lower,
            upper=upper,
            vol_ratio=vol_ratio,
            filled=filled,
            closes=closes,
            highs=highs,
            lows=lows,
            ma=ma,
            i=i,
        )
        notes.append(
            GapNote(
                date=pd.Timestamp(index[i]).date().isoformat(),
                kind=kind,
                direction=direction,
                gap_pct=gap_pct,
                lower=round(float(lower), 2),
                upper=round(float(upper), 2),
                filled=filled,
                volume_ratio=(round(vol_ratio, 2) if vol_ratio is not None else None),
                note=note,
            )
        )

    notes.reverse()  # most-recent first
    return notes[:max_notes]


def _volume_ratio(vols: np.ndarray, i: int) -> float | None:
    """Gap-day volume ÷ the trailing ~50-bar average (prior bars only)."""
    lo = max(0, i - _VOL_AVG_BARS)
    prior = vols[lo:i]
    if len(prior) == 0:
        return None
    avg = float(prior.mean())
    if avg <= 0:
        return None
    return float(vols[i]) / avg


def _is_filled(
    highs: np.ndarray,
    lows: np.ndarray,
    i: int,
    lower: float,
    upper: float,
    direction: str,
) -> bool:
    """A later bar traded back into the gap zone (up gap filled if a low re-enters
    it; down gap filled if a high re-enters it)."""
    for j in range(i + 1, len(highs)):
        if direction == "up" and lows[j] <= lower:
            return True
        if direction == "down" and highs[j] >= upper:
            return True
    return False


def _is_common(
    gap_pct: float,
    highs: np.ndarray,
    lows: np.ndarray,
    i: int,
    filled: bool,
) -> bool:
    """A common gap is small *or* sits inside a congestion range and fills quickly —
    it carries no real signal, so we suppress it."""
    if gap_pct < _COMMON_GAP_PCT:
        return True
    # In-congestion: the prior ~20 bars are a tight range and the gap got filled.
    lo = max(0, i - 20)
    prior_hi = float(highs[lo:i].max()) if i > lo else highs[i]
    prior_lo = float(lows[lo:i].min()) if i > lo else lows[i]
    mid = (prior_hi + prior_lo) / 2.0
    range_pct = (prior_hi - prior_lo) / mid * 100.0 if mid else 0.0
    in_congestion = range_pct <= _TIGHT_RANGE_PCT * 0.6  # very tight base
    # Filled small gaps inside congestion are the textbook "common" gap.
    return bool(filled and in_congestion and gap_pct < _COMMON_GAP_PCT * 2)


def _prior_range_pct(highs: np.ndarray, lows: np.ndarray, i: int, bars: int) -> float:
    """Width of the ``bars`` bars *before* the gap, as a % of their midpoint."""
    lo = max(0, i - bars)
    if i <= lo:
        return 100.0
    hi = float(highs[lo:i].max())
    lw = float(lows[lo:i].min())
    mid = (hi + lw) / 2.0
    return (hi - lw) / mid * 100.0 if mid else 100.0


def _classify(
    *,
    direction: str,
    gap_pct: float,
    lower: float,
    upper: float,
    vol_ratio: float | None,
    filled: bool,
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    ma: np.ndarray,
    i: int,
) -> tuple[str, str]:
    """Map a significant gap to breakaway / runaway / exhaustion + a plain-English
    note. Uses the prior-range tightness, the gap's position vs the ~50-bar MA, the
    volume ratio, and whether it later filled.
    """
    prior_range = _prior_range_pct(highs, lows, i, 30)
    based = prior_range <= _TIGHT_RANGE_PCT  # came out of a tight consolidation
    # How stretched price is vs its ~50-bar MA at the gap (sign by direction).
    ma_i = float(ma[i]) if ma[i] else float(closes[i])
    stretch = (float(closes[i]) - ma_i) / ma_i * 100.0 if ma_i else 0.0
    extended = (stretch >= _STRETCHED_PCT) if direction == "up" else (
        stretch <= -_STRETCHED_PCT
    )
    heavy = vol_ratio is not None and vol_ratio >= _HEAVY_VOL
    vol_txt = f"{vol_ratio:.1f}×" if vol_ratio is not None else "n/a"
    zone = f"{round(lower, 2)}–{round(upper, 2)}"
    role = "support" if direction == "up" else "resistance"

    # Exhaustion: near the end of an extended move and it filled (climactic).
    if extended and filled:
        return (
            "exhaustion",
            f"Exhaustion gap {direction} after an extended run "
            f"(~{abs(stretch):.0f}% past the 50-bar MA) on {vol_txt} volume; "
            f"already filled — caution, the move may be tiring at {zone}.",
        )

    # Breakaway: out of a tight base, ideally on heavy volume and unfilled.
    if based and not filled:
        vol_clause = f"on {vol_txt} volume" if heavy else f"({vol_txt} volume)"
        return (
            "breakaway",
            f"Breakaway gap {direction} out of a tight base {vol_clause}; "
            f"unfilled — acts as {role} at {zone}.",
        )

    # Runaway / measuring: mid-trend continuation, not from a base, still unfilled.
    if not filled:
        return (
            "runaway",
            f"Runaway (measuring) gap {direction} mid-trend on {vol_txt} volume; "
            f"unfilled — confirms momentum, {role} at {zone}.",
        )

    # Filled, not extended, not from a base: treat as a weak runaway with a caveat.
    return (
        "runaway",
        f"Runaway gap {direction} on {vol_txt} volume; later filled — momentum "
        f"signal only, watch {zone}.",
    )


# --- convenience --------------------------------------------------------------


def attention(
    df: pd.DataFrame,
    current_price: float | None = None,
) -> tuple[list[KeyLevel], list[GapNote]]:
    """Convenience: ``(key_levels(df, current_price), detect_gaps(df))``."""
    return key_levels(df, current_price), detect_gaps(df)
