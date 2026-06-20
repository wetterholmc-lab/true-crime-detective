"""Create and update the lifetime detective record for each player."""

from __future__ import annotations

from typing import Any

from agent.agents.detective.models import PlayerRecord, Score
from agent.services import db


def _row_to_player(row: Any) -> PlayerRecord:
    return PlayerRecord(
        telegram_id=row["telegram_id"],
        cases_attempted=row["cases_attempted"],
        cases_correct=row["cases_correct"],
        cases_wrong_verdict=row["cases_wrong_verdict"],
        cases_wrong_person=row["cases_wrong_person"],
        cases_abandoned=row["cases_abandoned"],
    )


async def get_or_create_player(telegram_id: int) -> PlayerRecord:
    row = await db.fetchrow(
        """
        INSERT INTO detective_players (telegram_id)
        VALUES ($1)
        ON CONFLICT (telegram_id) DO UPDATE SET last_active_at = now()
        RETURNING *
        """,
        telegram_id,
    )
    if not row:
        raise RuntimeError(f"Failed to upsert player {telegram_id}")
    return _row_to_player(row)


async def record_outcome(telegram_id: int, score: Score | None) -> None:
    """Increment the relevant counter for a completed or abandoned case."""
    col = {
        Score.CORRECT: "cases_correct",
        Score.WRONG_VERDICT: "cases_wrong_verdict",
        Score.WRONG_PERSON: "cases_wrong_person",
        None: "cases_abandoned",
    }[score]
    # col is one of four names we control — not user input — safe to interpolate.
    await db.execute(
        f"""
        UPDATE detective_players
        SET cases_attempted = cases_attempted + 1,
            {col} = {col} + 1,
            last_active_at = now()
        WHERE telegram_id = $1
        """,
        telegram_id,
    )


async def get_player_record(telegram_id: int) -> PlayerRecord:
    row = await db.fetchrow("SELECT * FROM detective_players WHERE telegram_id = $1", telegram_id)
    if not row:
        return await get_or_create_player(telegram_id)
    return _row_to_player(row)


async def is_authenticated(telegram_id: int) -> bool:
    """Return True if the player has entered the correct password."""
    row = await db.fetchrow(
        "SELECT authenticated FROM detective_players WHERE telegram_id = $1", telegram_id
    )
    return bool(row and row["authenticated"])


async def set_authenticated(telegram_id: int) -> None:
    """Mark a player as authenticated. Upserts so it works before /start."""
    await db.execute(
        "INSERT INTO detective_players (telegram_id, authenticated) VALUES ($1, true) "
        "ON CONFLICT (telegram_id) DO UPDATE SET authenticated = true",
        telegram_id,
    )
