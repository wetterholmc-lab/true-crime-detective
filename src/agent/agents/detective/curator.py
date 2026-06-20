"""Ingest one historical case into the detective database.

Usage:
    uv run detective-ingest --file path/to/transcript.txt --slug muller-1864
    uv run detective-ingest --file transcript.txt --slug muller-1864 --dry-run

How to get a transcript from Old Bailey Online (oldbaileyonline.org):
1. Search for a trial by name, date, or crime type
2. Open the full trial record page
3. Copy the complete trial text (or download the plain-text version)
4. Save it as a .txt file and pass it here with --file

The script will:
  1. Read the transcript from the file
  2. Call an LLM to extract structured case data (brief, cast, evidence, verdict)
  3. Refuse to proceed if no verdict is found (hard gate)
  4. Chunk the transcript with overlap
  5. Embed all chunks (baai/bge-m3 via OpenRouter)
  6. Store everything in Neon: detective_cases + detective_chunks

Running it twice with the same --slug is safe (ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from agent.agents.detective import chunk_store
from agent.agents.detective.models import CastMember, EvidenceItem, Verdict
from agent.logging_setup import setup_logging
from agent.services import db
from agent.services.llm import build_model, embed

MIGRATIONS_DIR = Path(__file__).parents[4] / "migrations"
CHUNK_SIZE = 400  # words per chunk
CHUNK_OVERLAP = 50  # words of overlap between adjacent chunks


class CaseTransform(BaseModel):
    """Structured case data extracted from a raw trial transcript by the LLM."""

    title: str = Field(description="Full case title, e.g. 'THE PEOPLE v. FRANZ MÜLLER'")
    court: str = Field(default="Old Bailey", description="Court name")
    year: int = Field(description="Year of the trial")
    accused_name: str = Field(description="Full name of the accused person")
    crime: str = Field(description="The charge, in 5–10 words")
    brief: str = Field(
        description=(
            "3–4 sentence case opening. Gripping and factual — this is the game intro. "
            "Describe who is accused of what, where, and the key dramatic fact."
        )
    )
    cast: list[CastMember] = Field(
        description="The people in the case: accused, victim(s), key witnesses (5–8 max)"
    )
    evidence: list[EvidenceItem] = Field(
        description=(
            "5–8 significant evidence items that appear in the transcript. "
            "Each needs an id ('e1', 'e2', ...), a short label, and a one-sentence summary."
        )
    )
    verdict: Verdict = Field(description="The real verdict: 'guilty' or 'not_guilty'")
    verdict_text: str = Field(description="1–2 sentences: what the jury decided and when")
    aftermath_text: str = Field(
        description="2–3 sentences: the sentence passed, execution or acquittal, public reaction"
    )


_transformer: Agent[None, CaseTransform] = Agent(
    build_model("smart"),
    output_type=CaseTransform,
    system_prompt=(
        "You are transforming a raw historical trial transcript into structured game data "
        "for a detective mystery game. Extract and structure the information carefully.\n\n"
        "Rules:\n"
        "- Extract only what the transcript actually states. Never invent.\n"
        "- The brief must be gripping but factual — it is the game's opening hook.\n"
        "- List evidence items that are actually mentioned and significant in the transcript.\n"
        "- Assign evidence ids sequentially: e1, e2, e3, ...\n"
        "- The verdict must come directly from the record. If unclear, note the ambiguity "
        "in verdict_text and use your best reading of the record.\n"
        "- aftermath_text covers sentence, execution, acquittal reaction, what followed."
    ),
)


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(words):
        chunk = words[i : i + size]
        chunks.append(" ".join(chunk))
        if i + size >= len(words):
            break
        i += size - overlap
    return chunks


async def ingest(slug: str, transcript: str, dry_run: bool = False) -> None:
    word_count = len(transcript.split())
    logger.info("Read {} words", word_count)

    logger.info("Transforming transcript with LLM (smart tier)...")
    result = await _transformer.run(f"TRANSCRIPT:\n\n{transcript}")
    t = result.output
    logger.info("Extracted: {} — verdict: {}", t.title, t.verdict)
    logger.info("{} cast members, {} evidence items", len(t.cast), len(t.evidence))

    if dry_run:
        logger.info("Dry run — printing result and exiting (nothing written to DB)")
        print(t.model_dump_json(indent=2))
        return

    await db.apply_migrations(MIGRATIONS_DIR)

    row = await db.fetchrow(
        """
        INSERT INTO detective_cases
            (slug, title, court, year, accused_name, crime, brief,
             cast_json, evidence_json, verdict, verdict_text, aftermath_text)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10,$11,$12)
        ON CONFLICT (slug) DO NOTHING
        RETURNING id
        """,
        slug,
        t.title,
        t.court,
        t.year,
        t.accused_name,
        t.crime,
        t.brief,
        json.dumps([m.model_dump() for m in t.cast]),
        json.dumps([e.model_dump() for e in t.evidence]),
        t.verdict.value,
        t.verdict_text,
        t.aftermath_text,
    )

    if row is None:
        logger.warning("Case '{}' already exists — skipping", slug)
        return

    case_id: int = row["id"]
    logger.info("Stored case id={}", case_id)

    chunks = _chunk_text(transcript)
    logger.info("Chunked into {} pieces — embedding...", len(chunks))
    embeddings = await embed(chunks)

    await chunk_store.store_chunks(case_id, chunks, embeddings)
    logger.info("Stored {} embedded chunks. Done.", len(chunks))


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Ingest a historical case transcript into the detective database"
    )
    parser.add_argument("--file", required=True, type=Path, help="Path to transcript .txt file")
    parser.add_argument("--slug", required=True, help="Unique slug, e.g. 'muller-1864'")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the LLM extraction without writing to the database",
    )
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"File not found: {args.file}")

    transcript = args.file.read_text(encoding="utf-8").strip()
    if not transcript:
        raise SystemExit(f"File is empty: {args.file}")

    asyncio.run(ingest(slug=args.slug, transcript=transcript, dry_run=args.dry_run))
