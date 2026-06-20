"""Read cases and evidence items from the database."""

from __future__ import annotations

from typing import Any

from agent.agents.detective.models import CaseRecord, CastMember, EvidenceItem, Verdict
from agent.services import db


def _row_to_case(row: Any) -> CaseRecord:
    return CaseRecord(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        court=row["court"],
        year=row["year"],
        accused_name=row["accused_name"],
        crime=row["crime"],
        brief=row["brief"],
        cast=[CastMember(**m) for m in row["cast_json"]],
        evidence=[EvidenceItem(**e) for e in row["evidence_json"]],
        verdict=Verdict(row["verdict"]),
        verdict_text=row["verdict_text"],
        aftermath_text=row["aftermath_text"],
    )


async def get_next_case(telegram_id: int) -> CaseRecord | None:
    """Return the first active case this player has not yet played, or None."""
    row = await db.fetchrow(
        """
        SELECT c.*
        FROM detective_cases c
        WHERE c.active = true
          AND c.id NOT IN (
              SELECT case_id
              FROM detective_sessions
              WHERE telegram_id = $1
                AND status IN ('solved', 'abandoned')
          )
        ORDER BY c.id ASC
        LIMIT 1
        """,
        telegram_id,
    )
    return _row_to_case(row) if row else None


async def get_case(case_id: int) -> CaseRecord:
    row = await db.fetchrow("SELECT * FROM detective_cases WHERE id = $1", case_id)
    if not row:
        raise ValueError(f"Case {case_id} not found")
    return _row_to_case(row)


async def get_evidence_item(case_id: int, ref: str | int) -> EvidenceItem | None:
    """Look up an evidence item by 1-based index or label substring."""
    case = await get_case(case_id)
    if isinstance(ref, int):
        idx = ref - 1
        return case.evidence[idx] if 0 <= idx < len(case.evidence) else None
    ref_lower = ref.lower().strip()
    for item in case.evidence:
        if ref_lower in item.label.lower() or item.id == ref_lower:
            return item
    return None
