"""Tests for The True-Crime Detective — stage 6: atomic module tests in isolation.

All offline tests run by default.  Integration tests (live LLM / real DB) are
marked `integration` and excluded from the default run:

    uv run pytest                          # offline only
    uv run pytest -m integration           # live tests (needs credentials)
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Provide a fake key so Settings validates without a real .env.
# Tests that actually call the API are marked `integration` and guarded by
# `requires_llm` / `requires_db` below.
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-real")

from agent.agents.detective.models import (
    AccusationExtract,
    CaseRecord,
    CastMember,
    ChunkResult,
    EvidenceItem,
    Score,
    SessionStatus,
    Verdict,
)

# ---------------------------------------------------------------------------
# Guards for live tests
# ---------------------------------------------------------------------------


def _llm_ready() -> bool:
    try:
        from agent.config import get_settings

        key = get_settings().openrouter_api_key
        return bool(key) and key != "test-key-not-real"
    except Exception:
        return False


def _db_ready() -> bool:
    try:
        from agent.config import get_settings

        return bool(get_settings().database_url)
    except Exception:
        return False


requires_llm = pytest.mark.skipif(not _llm_ready(), reason="OPENROUTER_API_KEY not set")
requires_db = pytest.mark.skipif(not _db_ready(), reason="DATABASE_URL not set")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_case(**overrides: object) -> CaseRecord:
    defaults: dict[str, object] = dict(
        id=1,
        slug="muller-1864",
        title="THE PEOPLE v. FRANZ MÜLLER",
        court="Old Bailey",
        year=1864,
        accused_name="Franz Müller",
        crime="Murder by blunt force on the North London Railway",
        brief=(
            "Thomas Briggs, a 69-year-old bank clerk, was found dying on the tracks of "
            "the North London Railway on the night of 9 July 1864. His skull had been "
            "fractured and his gold watch chain was missing. A hat found in the carriage "
            "did not belong to him. The accused: Franz Müller, a German tailor, 24, "
            "who had already sailed for New York before the body was identified."
        ),
        cast=[
            CastMember(name="Franz Müller", role="Accused", description="A German tailor, 24"),
            CastMember(name="Thomas Briggs", role="Victim", description="A bank clerk, 69"),
            CastMember(name="John Death", role="Witness", description="A jeweller of Cheapside"),
        ],
        evidence=[
            EvidenceItem(id="e1", label="Müller's hat", summary="Left at the scene of the crime"),
            EvidenceItem(
                id="e2",
                label="Briggs's hat",
                summary="Found in Müller's possession in New York",
            ),
            EvidenceItem(
                id="e3",
                label="Gold watch chain",
                summary="Sold by Müller to Mr Death the jeweller",
            ),
        ],
        verdict=Verdict.GUILTY,
        verdict_text="Franz Müller was found GUILTY by the jury on 27 October 1864.",
        aftermath_text=(
            "He was executed at Newgate Prison on 14 November 1864, before a crowd of thousands."
        ),
    )
    defaults.update(overrides)
    return CaseRecord(**defaults)  # type: ignore[arg-type]


def _make_chunks(texts: list[str] | None = None) -> list[ChunkResult]:
    texts = texts or ["The prisoner was seen leaving the carriage at Hackney Wick station."]
    return [
        ChunkResult(case_id=1, chunk_index=i, text=t, similarity=0.9 - i * 0.05)
        for i, t in enumerate(texts)
    ]


# ---------------------------------------------------------------------------
# scorer — pure function, no I/O
# ---------------------------------------------------------------------------


def test_score_exact_name_and_matching_verdict() -> None:
    from agent.agents.detective.scorer import score_accusation

    extract = AccusationExtract(name="Franz Müller", verdict=Verdict.GUILTY)
    assert score_accusation(extract, _make_case()) == Score.CORRECT


def test_score_not_guilty_case_correct() -> None:
    from agent.agents.detective.scorer import score_accusation

    case = _make_case(verdict=Verdict.NOT_GUILTY)
    extract = AccusationExtract(name="Franz Müller", verdict=Verdict.NOT_GUILTY)
    assert score_accusation(extract, case) == Score.CORRECT


def test_score_right_person_wrong_verdict() -> None:
    from agent.agents.detective.scorer import score_accusation

    extract = AccusationExtract(name="Franz Müller", verdict=Verdict.NOT_GUILTY)
    assert score_accusation(extract, _make_case()) == Score.WRONG_VERDICT


def test_score_wrong_person() -> None:
    from agent.agents.detective.scorer import score_accusation

    extract = AccusationExtract(name="John Smith", verdict=Verdict.GUILTY)
    assert score_accusation(extract, _make_case()) == Score.WRONG_PERSON


def test_score_surname_only_matches() -> None:
    from agent.agents.detective.scorer import score_accusation

    # Players often type only the last name.
    extract = AccusationExtract(name="Müller", verdict=Verdict.GUILTY)
    assert score_accusation(extract, _make_case()) == Score.CORRECT


def test_score_case_insensitive() -> None:
    from agent.agents.detective.scorer import score_accusation

    extract = AccusationExtract(name="franz müller", verdict=Verdict.GUILTY)
    assert score_accusation(extract, _make_case()) == Score.CORRECT


def test_score_fuzzy_match_handles_missing_diacritic() -> None:
    from agent.agents.detective.scorer import score_accusation

    # "Muller" vs "Müller" — diacritics stripped by fuzzy ratio
    extract = AccusationExtract(name="Muller", verdict=Verdict.GUILTY)
    result = score_accusation(extract, _make_case())
    # Should be CORRECT or WRONG_VERDICT, never WRONG_PERSON
    assert result != Score.WRONG_PERSON


def test_score_victim_name_is_wrong_person() -> None:
    from agent.agents.detective.scorer import score_accusation

    # Player accidentally accuses the victim
    extract = AccusationExtract(name="Thomas Briggs", verdict=Verdict.GUILTY)
    assert score_accusation(extract, _make_case()) == Score.WRONG_PERSON


# ---------------------------------------------------------------------------
# models — Pydantic types validate as expected
# ---------------------------------------------------------------------------


def test_verdict_enum_values() -> None:
    assert Verdict.GUILTY.value == "guilty"
    assert Verdict.NOT_GUILTY.value == "not_guilty"


def test_score_enum_values() -> None:
    assert Score.CORRECT.value == "correct"
    assert Score.WRONG_VERDICT.value == "wrong_verdict"
    assert Score.WRONG_PERSON.value == "wrong_person"


def test_case_record_constructs_and_validates() -> None:
    case = _make_case()
    assert case.slug == "muller-1864"
    assert len(case.evidence) == 3
    assert case.evidence[0].id == "e1"
    assert case.verdict == Verdict.GUILTY


def test_accusation_extract_validates() -> None:
    a = AccusationExtract(name="Franz Müller", verdict=Verdict.GUILTY)
    assert a.name == "Franz Müller"
    assert a.verdict == Verdict.GUILTY


def test_session_status_enum() -> None:
    assert SessionStatus.ACTIVE.value == "active"
    assert SessionStatus.SOLVED.value == "solved"
    assert SessionStatus.ABANDONED.value == "abandoned"


# ---------------------------------------------------------------------------
# chunk_store — _vec (pure helper)
# ---------------------------------------------------------------------------


def test_vec_formats_list_as_pgvector_literal() -> None:
    from agent.agents.detective.chunk_store import _vec

    assert _vec([1.0, 2.0, 3.0]) == "[1.0,2.0,3.0]"


def test_vec_single_element() -> None:
    from agent.agents.detective.chunk_store import _vec

    assert _vec([0.5]) == "[0.5]"


# ---------------------------------------------------------------------------
# curator — _chunk_text (pure helper)
# ---------------------------------------------------------------------------


def test_chunk_text_empty_returns_empty_list() -> None:
    from agent.agents.detective.curator import _chunk_text

    assert _chunk_text("") == []
    assert _chunk_text("   ") == []


def test_chunk_text_short_text_is_one_chunk() -> None:
    from agent.agents.detective.curator import _chunk_text

    words = ["word"] * 10
    text = " ".join(words)
    chunks = _chunk_text(text, size=400)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_produces_overlap() -> None:
    from agent.agents.detective.curator import _chunk_text

    # 10 words, chunk size=6, overlap=2 → chunks share 2 words at each boundary
    words = [f"w{i}" for i in range(10)]
    text = " ".join(words)
    chunks = _chunk_text(text, size=6, overlap=2)

    assert len(chunks) == 2
    # Last 2 words of chunk 0 == first 2 words of chunk 1
    end_of_first = chunks[0].split()[-2:]
    start_of_second = chunks[1].split()[:2]
    assert end_of_first == start_of_second


def test_chunk_text_count_for_known_input() -> None:
    from agent.agents.detective.curator import _chunk_text

    # 10 words, size=6, overlap=2 → step=4 → chunks at 0, 4 → 2 chunks
    words = [f"w{i}" for i in range(10)]
    chunks = _chunk_text(" ".join(words), size=6, overlap=2)
    assert len(chunks) == 2


def test_chunk_text_no_empty_chunks() -> None:
    from agent.agents.detective.curator import _chunk_text

    text = "The quick brown fox jumped over the lazy dog by the river bank near the old mill."
    chunks = _chunk_text(text, size=5, overlap=1)
    assert all(len(c.strip()) > 0 for c in chunks)


# ---------------------------------------------------------------------------
# bot helpers — pure functions
# ---------------------------------------------------------------------------


def test_pct_zero_attempted_returns_zero() -> None:
    from agent.agents.detective.bot import _pct

    assert _pct(0, 0) == 0


def test_pct_all_correct() -> None:
    from agent.agents.detective.bot import _pct

    assert _pct(5, 5) == 100


def test_pct_three_of_four() -> None:
    from agent.agents.detective.bot import _pct

    assert _pct(3, 4) == 75


def test_score_lines_covers_all_score_values() -> None:
    from agent.agents.detective.bot import _SCORE_LINES

    # Every Score variant must have a line — missing one would mean a KeyError at runtime.
    for score in Score:
        assert score in _SCORE_LINES, f"Missing score line for {score}"


# ---------------------------------------------------------------------------
# game_master — mock the LLM; verify prompt structure
# ---------------------------------------------------------------------------


async def test_answer_question_includes_case_title_and_chunk() -> None:
    from agent.agents.detective.game_master import answer_question

    case = _make_case()
    chunks = _make_chunks(["The prisoner sold the gold chain to Mr Death on 10 July 1864."])

    mock_result = MagicMock()
    mock_result.output = "The record states the prisoner sold the chain."

    with patch("agent.agents.detective.game_master._gm") as mock_gm:
        mock_gm.run = AsyncMock(return_value=mock_result)
        result = await answer_question(case, chunks, "What happened to the chain?")

    prompt: str = mock_gm.run.call_args[0][0]
    assert case.title in prompt
    assert "Mr Death" in prompt
    assert "What happened to the chain?" in prompt
    assert result == "The record states the prisoner sold the chain."


async def test_generate_hint_includes_examined_list() -> None:
    from agent.agents.detective.game_master import generate_hint

    case = _make_case()
    chunks = _make_chunks(["The hat found in the carriage was smaller in the crown."])
    examined = ["e1", "e3"]

    mock_result = MagicMock()
    mock_result.output = "Consider the hat exchange, Detective."

    with patch("agent.agents.detective.game_master._gm") as mock_gm:
        mock_gm.run = AsyncMock(return_value=mock_result)
        hint = await generate_hint(case, chunks, examined)

    prompt: str = mock_gm.run.call_args[0][0]
    assert "e1" in prompt and "e3" in prompt
    assert hint == "Consider the hat exchange, Detective."


async def test_answer_question_handles_no_chunks() -> None:
    from agent.agents.detective.game_master import answer_question

    case = _make_case()

    mock_result = MagicMock()
    mock_result.output = "The record is silent on that, Detective."

    with patch("agent.agents.detective.game_master._gm") as mock_gm:
        mock_gm.run = AsyncMock(return_value=mock_result)
        result = await answer_question(case, [], "Who is the real killer?")

    prompt: str = mock_gm.run.call_args[0][0]
    assert "No relevant passages" in prompt  # the empty-chunk message appears in the prompt
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# accusation_extractor — mock the LLM
# ---------------------------------------------------------------------------


async def test_extract_returns_none_on_llm_exception() -> None:
    from agent.agents.detective.accusation_extractor import extract_accusation

    with patch("agent.agents.detective.accusation_extractor._extractor") as mock_ext:
        mock_ext.run = AsyncMock(side_effect=Exception("API unavailable"))
        result = await extract_accusation("I accuse Franz Müller. Guilty.")

    assert result is None


# ---------------------------------------------------------------------------
# Integration tests — live LLM (marked, skipped without credentials)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_llm
async def test_accusation_extractor_live_guilty() -> None:
    """Extractor pulls the right name and verdict from natural language."""
    from agent.agents.detective.accusation_extractor import extract_accusation

    result = await extract_accusation("I think it was Franz Müller. Definitely guilty.")

    assert result is not None
    assert "müller" in result.name.lower()
    assert result.verdict == Verdict.GUILTY


@pytest.mark.integration
@requires_llm
async def test_accusation_extractor_live_not_guilty() -> None:
    from agent.agents.detective.accusation_extractor import extract_accusation

    result = await extract_accusation("Adelaide Bartlett — not guilty. The evidence is too thin.")

    assert result is not None
    assert "bartlett" in result.name.lower()
    assert result.verdict == Verdict.NOT_GUILTY


@pytest.mark.integration
@requires_llm
async def test_game_master_answers_from_chunks_only() -> None:
    """Game master uses the retrieved passage and does not hallucinate beyond it."""
    from agent.agents.detective.game_master import answer_question

    case = _make_case()
    # Provide a chunk with one very specific invented fact
    chunks = _make_chunks(
        ["The prisoner had a distinctive blue tattoo on his left wrist, noted by all witnesses."]
    )

    result = await answer_question(case, chunks, "Did the prisoner have any distinguishing marks?")

    # The LLM should mention the tattoo from our chunk
    assert "tattoo" in result.lower() or "wrist" in result.lower() or "mark" in result.lower()
    # And it should not confidently reveal a verdict unprompted
    assert "guilty" not in result.lower() or "the record" in result.lower()


@pytest.mark.integration
@requires_llm
async def test_game_master_silent_when_no_relevant_chunk() -> None:
    """Game master says 'silent' when the chunk contains nothing relevant."""
    from agent.agents.detective.game_master import answer_question

    case = _make_case()
    # Chunk about something completely unrelated to the question
    chunks = _make_chunks(["The court opened at nine o'clock in the morning."])

    result = await answer_question(case, chunks, "What was the accused's childhood like?")

    # Should acknowledge the record doesn't speak to this
    assert "silent" in result.lower() or "record" in result.lower() or "not" in result.lower()
