"""Store and cosine-search embedded transcript chunks via pgvector."""

from __future__ import annotations

from agent.agents.detective.models import ChunkResult
from agent.services import db


def _vec(embedding: list[float]) -> str:
    """Format a float list as a pgvector literal: '[0.1,0.2,...]'."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def store_chunks(case_id: int, texts: list[str], embeddings: list[list[float]]) -> None:
    """Bulk-insert transcript chunks with their embeddings.

    Idempotent: skips silently if chunks already exist for this case.
    """
    existing = await db.fetchrow(
        "SELECT 1 FROM detective_chunks WHERE case_id = $1 LIMIT 1", case_id
    )
    if existing:
        return
    for idx, (text, emb) in enumerate(zip(texts, embeddings, strict=True)):
        await db.execute(
            """
            INSERT INTO detective_chunks (case_id, chunk_index, text, embedding)
            VALUES ($1, $2, $3, $4::vector)
            ON CONFLICT (case_id, chunk_index) DO NOTHING
            """,
            case_id,
            idx,
            text,
            _vec(emb),
        )


async def search_chunks(
    case_id: int, query_embedding: list[float], k: int = 5
) -> list[ChunkResult]:
    """Return the k most relevant chunks for a query, ranked by cosine similarity."""
    rows = await db.fetch(
        """
        SELECT case_id, chunk_index, text,
               1 - (embedding <=> $1::vector) AS similarity
        FROM detective_chunks
        WHERE case_id = $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        _vec(query_embedding),
        case_id,
        k,
    )
    return [
        ChunkResult(
            case_id=row["case_id"],
            chunk_index=row["chunk_index"],
            text=row["text"],
            similarity=float(row["similarity"]),
        )
        for row in rows
    ]
