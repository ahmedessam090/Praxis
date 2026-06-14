"""Read/write the screener tables (scanner candidates now; alpha + downgraded added in
later chunks). Symbol-keyed for natural dedup + clear/delete. Mirrors regime/repo.py."""

from __future__ import annotations

from sqlalchemy import select

from ta_assistant.db.models import AlphaItemRow, DowngradedItemRow, ScreenerCandidateRow
from ta_assistant.db.session import session_scope
from ta_assistant.synthesis.schema import (
    AlphaItem,
    AlphaVerdict,
    CandidateStatus,
    DowngradedItem,
    ScreenerCandidate,
)

# --- scanner candidates ---


def upsert_candidates(cands: list[ScreenerCandidate], db_path: str | None = None) -> int:
    with session_scope(db_path) as session:
        for c in cands:
            row = session.get(ScreenerCandidateRow, c.symbol)
            if row is None:
                session.add(
                    ScreenerCandidateRow(
                        symbol=c.symbol,
                        sector=c.sector,
                        score=c.score,
                        status=c.status.value,
                        payload_json=c.model_dump_json(),
                    )
                )
            else:
                row.sector = c.sector
                row.score = c.score
                row.status = c.status.value
                row.payload_json = c.model_dump_json()
    return len(cands)


def list_candidates(db_path: str | None = None) -> list[ScreenerCandidate]:
    with session_scope(db_path) as session:
        rows = session.execute(
            select(ScreenerCandidateRow).order_by(ScreenerCandidateRow.score.desc())
        ).scalars().all()
        return [ScreenerCandidate.model_validate_json(r.payload_json) for r in rows]


def get_candidate(symbol: str, db_path: str | None = None) -> ScreenerCandidate | None:
    with session_scope(db_path) as session:
        row = session.get(ScreenerCandidateRow, symbol.upper())
        return ScreenerCandidate.model_validate_json(row.payload_json) if row else None


def set_candidate_status(
    symbol: str,
    status: CandidateStatus,
    verdict: AlphaVerdict | None = None,
    db_path: str | None = None,
) -> None:
    with session_scope(db_path) as session:
        row = session.get(ScreenerCandidateRow, symbol.upper())
        if row is None:
            return
        cand = ScreenerCandidate.model_validate_json(row.payload_json)
        cand.status = status
        if verdict is not None:
            cand.verdict = verdict  # so the Scanner row can show why (alpha OR not)
        row.status = status.value
        row.payload_json = cand.model_dump_json()


def delete_candidate(symbol: str, db_path: str | None = None) -> None:
    with session_scope(db_path) as session:
        row = session.get(ScreenerCandidateRow, symbol.upper())
        if row is not None:
            session.delete(row)


def clear_candidates(db_path: str | None = None) -> int:
    with session_scope(db_path) as session:
        rows = session.execute(select(ScreenerCandidateRow)).scalars().all()
        for r in rows:
            session.delete(r)
        return len(rows)


def existing_symbols(db_path: str | None = None) -> set[str]:
    """All symbols already known to the screener (candidates + alpha + downgraded), so a
    fresh scan never re-suggests a name we're already tracking."""
    with session_scope(db_path) as session:
        out: set[str] = set()
        for model in (ScreenerCandidateRow, AlphaItemRow, DowngradedItemRow):
            out.update(session.execute(select(model.symbol)).scalars().all())
        return out


# --- alpha list ---


def upsert_alpha(item: AlphaItem, db_path: str | None = None) -> None:
    with session_scope(db_path) as session:
        row = session.get(AlphaItemRow, item.symbol.upper())
        if row is None:
            session.add(
                AlphaItemRow(
                    symbol=item.symbol,
                    conviction=item.verdict.conviction,
                    sector=item.verdict.sector,
                    analysis_generated_at=item.analysis_generated_at,
                    payload_json=item.model_dump_json(),
                )
            )
        else:
            row.conviction = item.verdict.conviction
            row.sector = item.verdict.sector
            row.analysis_generated_at = item.analysis_generated_at
            row.payload_json = item.model_dump_json()


def list_alpha(db_path: str | None = None) -> list[AlphaItem]:
    with session_scope(db_path) as session:
        rows = (
            session.execute(select(AlphaItemRow).order_by(AlphaItemRow.conviction.desc()))
            .scalars()
            .all()
        )
        return [AlphaItem.model_validate_json(r.payload_json) for r in rows]


def get_alpha(symbol: str, db_path: str | None = None) -> AlphaItem | None:
    with session_scope(db_path) as session:
        row = session.get(AlphaItemRow, symbol.upper())
        return AlphaItem.model_validate_json(row.payload_json) if row else None


def delete_alpha(symbol: str, db_path: str | None = None) -> None:
    with session_scope(db_path) as session:
        row = session.get(AlphaItemRow, symbol.upper())
        if row is not None:
            session.delete(row)


# --- downgraded ---


def upsert_downgraded(item: DowngradedItem, db_path: str | None = None) -> None:
    with session_scope(db_path) as session:
        row = session.get(DowngradedItemRow, item.symbol.upper())
        if row is None:
            session.add(
                DowngradedItemRow(
                    symbol=item.symbol,
                    payload_json=item.model_dump_json(),
                    downgraded_at=item.downgraded_at,
                )
            )
        else:
            row.payload_json = item.model_dump_json()
            row.downgraded_at = item.downgraded_at


def list_downgraded(db_path: str | None = None) -> list[DowngradedItem]:
    with session_scope(db_path) as session:
        rows = (
            session.execute(
                select(DowngradedItemRow).order_by(DowngradedItemRow.downgraded_at.desc())
            )
            .scalars()
            .all()
        )
        return [DowngradedItem.model_validate_json(r.payload_json) for r in rows]


def move_to_downgraded(item: DowngradedItem, db_path: str | None = None) -> None:
    """Atomically remove from the alpha list, record in downgraded, AND mark the scanner
    candidate not-alpha — all in ONE transaction (no half-applied state on a crash)."""
    sym = item.symbol.upper()
    with session_scope(db_path) as session:
        alpha = session.get(AlphaItemRow, sym)
        if alpha is not None:
            session.delete(alpha)
        if session.get(DowngradedItemRow, sym) is None:
            session.add(
                DowngradedItemRow(
                    symbol=sym,
                    payload_json=item.model_dump_json(),
                    downgraded_at=item.downgraded_at,
                )
            )
        cand = session.get(ScreenerCandidateRow, sym)
        if cand is not None:
            sc = ScreenerCandidate.model_validate_json(cand.payload_json)
            sc.status = CandidateStatus.NOT_ALPHA
            cand.status = CandidateStatus.NOT_ALPHA.value
            cand.payload_json = sc.model_dump_json()
