"""Open, update, and close player investigation sessions."""

from __future__ import annotations

import json
from typing import Any

from agent.agents.detective.models import Score, Session, SessionStatus, Verdict
from agent.services import db


def _row_to_session(row: Any) -> Session:
    return Session(
        id=row["id"],
        telegram_id=row["telegram_id"],
        case_id=row["case_id"],
        status=SessionStatus(row["status"]),
        clues_examined=list(row["clues_examined"]),
        hint_count=row["hint_count"],
        pending_accusation=row["pending_accusation"],
        accusation_name=row["accusation_name"],
        accusation_verdict=Verdict(row["accusation_verdict"])
        if row["accusation_verdict"]
        else None,
        score=Score(row["score"]) if row["score"] else None,
        last_active_at=row["last_active_at"],
    )


async def get_active_session(telegram_id: int) -> Session | None:
    row = await db.fetchrow(
        "SELECT * FROM detective_sessions WHERE telegram_id = $1 AND status = 'active' LIMIT 1",
        telegram_id,
    )
    return _row_to_session(row) if row else None


async def open_session(telegram_id: int, case_id: int) -> Session:
    row = await db.fetchrow(
        """
        INSERT INTO detective_sessions (telegram_id, case_id)
        VALUES ($1, $2)
        RETURNING *
        """,
        telegram_id,
        case_id,
    )
    if not row:
        raise RuntimeError("Failed to open session")
    return _row_to_session(row)


async def mark_evidence_examined(session_id: int, evidence_id: str) -> None:
    row = await db.fetchrow(
        "SELECT clues_examined FROM detective_sessions WHERE id = $1", session_id
    )
    if not row:
        return
    examined: list[str] = list(row["clues_examined"])
    if evidence_id not in examined:
        examined.append(evidence_id)
    await db.execute(
        "UPDATE detective_sessions SET clues_examined = $1::jsonb WHERE id = $2",
        json.dumps(examined),
        session_id,
    )


async def set_pending_accusation(session_id: int, pending: bool) -> None:
    await db.execute(
        "UPDATE detective_sessions "
        "SET pending_accusation = $1, last_active_at = now() WHERE id = $2",
        pending,
        session_id,
    )


async def increment_hint_count(session_id: int) -> None:
    await db.execute(
        "UPDATE detective_sessions "
        "SET hint_count = hint_count + 1, last_active_at = now() WHERE id = $1",
        session_id,
    )


async def close_session(
    session_id: int,
    status: SessionStatus,
    accusation_name: str | None = None,
    accusation_verdict: Verdict | None = None,
    score: Score | None = None,
) -> None:
    await db.execute(
        """
        UPDATE detective_sessions
        SET status = $1,
            accusation_name = $2,
            accusation_verdict = $3,
            score = $4,
            closed_at = now(),
            last_active_at = now()
        WHERE id = $5
        """,
        status.value,
        accusation_name,
        accusation_verdict.value if accusation_verdict else None,
        score.value if score else None,
        session_id,
    )


async def touch_session(session_id: int) -> None:
    await db.execute(
        "UPDATE detective_sessions SET last_active_at = now() WHERE id = $1",
        session_id,
    )


async def get_stale_sessions(threshold_hours: int = 24) -> list[Session]:
    """Return active sessions with no activity for at least threshold_hours."""
    rows = await db.fetch(
        """
        SELECT * FROM detective_sessions
        WHERE status = 'active'
          AND last_active_at < now() - ($1 * interval '1 hour')
        """,
        threshold_hours,
    )
    return [_row_to_session(r) for r in rows]
