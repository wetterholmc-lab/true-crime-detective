"""Domain types for The True-Crime Detective.

All types are Pydantic models or StrEnums so they are validated, typed,
and serialisable. No I/O here — just the shapes.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Verdict(StrEnum):
    GUILTY = "guilty"
    NOT_GUILTY = "not_guilty"


class Score(StrEnum):
    CORRECT = "correct"
    WRONG_VERDICT = "wrong_verdict"
    WRONG_PERSON = "wrong_person"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    SOLVED = "solved"
    ABANDONED = "abandoned"


class CastMember(BaseModel):
    name: str
    role: str
    description: str


class EvidenceItem(BaseModel):
    id: str = Field(description="Short identifier, e.g. 'e1'")
    label: str = Field(description="Display name, e.g. 'The railway ticket stub'")
    summary: str = Field(description="One sentence from the record about this item")


class CaseRecord(BaseModel):
    id: int
    slug: str
    title: str
    court: str
    year: int
    accused_name: str
    crime: str
    brief: str
    cast: list[CastMember]
    evidence: list[EvidenceItem]
    verdict: Verdict
    verdict_text: str
    aftermath_text: str


class ChunkResult(BaseModel):
    case_id: int
    chunk_index: int
    text: str
    similarity: float


class Session(BaseModel):
    id: int
    telegram_id: int
    case_id: int
    status: SessionStatus
    clues_examined: list[str]
    hint_count: int
    pending_accusation: bool
    accusation_name: str | None
    accusation_verdict: Verdict | None
    score: Score | None
    last_active_at: datetime


class PlayerRecord(BaseModel):
    telegram_id: int
    cases_attempted: int
    cases_correct: int
    cases_wrong_verdict: int
    cases_wrong_person: int
    cases_abandoned: int


class AccusationExtract(BaseModel):
    """Structured output from the accusation extractor LLM."""

    name: str = Field(description="Name of the person the player is accusing (may be partial)")
    verdict: Verdict = Field(description="Player's verdict: guilty or not_guilty")
