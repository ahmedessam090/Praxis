"""Consensus layer: collapse redundant candidate labels into distinct STRUCTURES,
then pick the 1-3 that describe the chart's big picture.

The engine deliberately over-generates — many detectors fire on one consolidation, and
multi-scale detection adds even more. Here we:

1. **Cluster** candidates that describe the same structure (same direction, overlapping
   time-region, near-equal breakout) and keep ONE representative per cluster.
2. **Assign roles** — primary / secondary (a nested continuation) / cap (an interlocking
   bearish ceiling) — deterministically; everything else becomes "considered".

The vision step (validator) may later override these picks and relabel them. This module
is the no-LLM baseline, so the tool stays fully functional with no API key.
"""

from __future__ import annotations

from collections.abc import Sequence

from ta_assistant.synthesis.schema import DetectedPattern, Timeframe

_STATUS_RANK = {"triggered": 3, "confirmed": 2, "forming": 1, "invalidated": 0}
# Continuation structures that make a natural SECONDARY read nested in a larger base.
_CONTINUATION = {"bull_flag", "pennant", "ascending_channel"}
# Headline prefers the swing trader's working canvas (weekly), then daily, then the
# big-picture monthly — but only as a tie-break after actionability.
_TF_WEIGHT = {Timeframe.WEEKLY: 3, Timeframe.DAILY: 2, Timeframe.MONTHLY: 1}

PRIMARY = "primary"
SECONDARY = "secondary"
CAP = "cap"
CONSIDERED = "considered"

# A marginal/low-confidence pattern is NOT surfaced as the trade — the timeframe is then
# treated as having no clean core setup (rather than fabricating one). The clean-rail and
# flat-neckline detector gates already reject scattered geometry; this is the backstop.
_MIN_PRIMARY_CONF = 0.6


def _overlap_ratio(a: DetectedPattern, b: DetectedPattern) -> float:
    """Intersection over the SMALLER region, so a short structure fully nested inside a
    longer one (e.g. a double-bottom inside a cup) scores ~1.0 and they cluster together."""
    lo = max(a.region_start, b.region_start)
    hi = min(a.region_end, b.region_end)
    if hi <= lo:
        return 0.0
    inter = (hi - lo).total_seconds()
    span = min(
        (a.region_end - a.region_start).total_seconds(),
        (b.region_end - b.region_start).total_seconds(),
    )
    return inter / span if span > 0 else 0.0


def _same_structure(a: DetectedPattern, b: DetectedPattern) -> bool:
    """Two candidates describe the same structure if same direction, their regions
    overlap substantially, and they watch a near-equal breakout level."""
    if a.direction != b.direction or a.timeframe != b.timeframe:
        return False
    ratio = _overlap_ratio(a, b)
    if ratio < 0.5:
        return False
    ea, eb = a.entry, b.entry
    if ea is None or eb is None or ea <= 0:
        return ratio >= 0.7  # no breakout to compare — lean on strong time overlap
    return abs(ea - eb) / ea <= 0.06


def _rep_key(p: DetectedPattern) -> tuple[float, int, object, int]:
    """Ranking key (higher is better). Confidence leads — a clean, well-defined structure
    beats a marginal one that merely happens to have triggered — with status, a more recent
    right edge (the live read), and pivot count as tie-breaks."""
    status = _STATUS_RANK.get(p.status.value, 0)
    return (round(p.confidence, 3), status, p.region_end, len(p.pivots))


def cluster_candidates(patterns: Sequence[DetectedPattern]) -> list[list[DetectedPattern]]:
    """Cluster same-structure candidates via connected components (union-find), so the
    result is order-independent and transitive — a cup and a double-bottom that each
    describe the consolidation at one breakout end up in the same cluster regardless of
    detection order."""
    items = list(patterns)
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _same_structure(items[i], items[j]):
                parent[find(i)] = find(j)

    groups: dict[int, list[DetectedPattern]] = {}
    for idx, item in enumerate(items):
        groups.setdefault(find(idx), []).append(item)
    return list(groups.values())


def assign_consensus(patterns: Sequence[DetectedPattern]) -> None:
    """Deterministic baseline: dedup to representatives + assign primary/secondary/cap
    roles per timeframe. Mutates each pattern's `cluster_id` and `role` in place.

    Call AFTER assign_nesting + assign_conflicts so parent/conflict links are available.
    """
    if not patterns:
        return
    clusters = cluster_candidates(patterns)
    reps: list[DetectedPattern] = []
    member_ids: dict[int, set[str]] = {}
    for cid, cl in enumerate(clusters):
        member_ids[cid] = {p.id for p in cl}
        for p in cl:
            p.cluster_id = cid
            p.role = CONSIDERED
        # a CORE pattern always represents its cluster over a SUPPORT one (e.g. a rectangle
        # over a double-bottom describing the same base) so the tradeable read isn't lost.
        reps.append(max(cl, key=lambda q: (q.tier == "core", _rep_key(q))))

    for tf in {r.timeframe for r in reps}:
        tf_reps = [r for r in reps if r.timeframe == tf]
        # primary/secondary must be CORE (tradeable) structures — a rounding/double/triple
        # bottom (tier=support) strengthens a setup but is never the trade itself.
        bulls = sorted(
            (
                r
                for r in tf_reps
                if r.direction == "bullish"
                and r.tier == "core"
                and r.confidence >= _MIN_PRIMARY_CONF  # drop marginal patterns from the trade
            ),
            key=_rep_key,
            reverse=True,
        )
        bears = sorted(
            (r for r in tf_reps if r.direction == "bearish"), key=_rep_key, reverse=True
        )
        if not bulls:
            if bears:  # no long setup — surface the dominant bearish structure as context
                bears[0].role = CAP
            continue

        primary = bulls[0]
        primary.role = PRIMARY

        # secondary: a DIFFERENT bullish structure — prefer a continuation nested with primary
        secondary = next(
            (
                r
                for r in bulls[1:]
                if r.pattern_type in _CONTINUATION
                or r.parent_id == primary.id
                or primary.parent_id == r.id
            ),
            None,
        )
        if secondary is None and len(bulls) > 1:
            secondary = bulls[1]
        if secondary is not None:
            secondary.role = SECONDARY

        # cap: prefer a bearish structure that interlocks with primary (the interlock link may
        # point at a clustered-away member, so check the whole cluster), else the strongest bear.
        conflict_ids = set(primary.conflicts_with)
        cap = next(
            (
                b
                for b in bears
                if b.cluster_id is not None and member_ids[b.cluster_id] & conflict_ids
            ),
            None,
        ) or (bears[0] if bears else None)
        if cap is not None:
            cap.role = CAP


def pick_headline(patterns: Sequence[DetectedPattern]) -> DetectedPattern | None:
    """The single best long setup for the summary headline. The monthly is big-picture
    context — only headline it when no weekly/daily primary exists — so a year-old monthly
    base never eclipses the live setup on the trader's canvas."""
    primaries = [p for p in patterns if p.role == PRIMARY]
    if not primaries:
        return None
    near = [p for p in primaries if p.timeframe != Timeframe.MONTHLY]
    pool = near or primaries
    return max(
        pool,
        key=lambda p: (
            _TF_WEIGHT.get(p.timeframe, 0),
            round(p.confidence, 3),
            _STATUS_RANK.get(p.status.value, 0),
        ),
    )
