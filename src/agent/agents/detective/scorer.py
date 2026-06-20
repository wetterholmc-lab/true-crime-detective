"""Score an accusation against the real case record. Pure function — no I/O.

Three possible outcomes:
  CORRECT       — right person AND right verdict
  WRONG_VERDICT — right person, wrong verdict (e.g. said Guilty when verdict was Not Guilty)
  WRONG_PERSON  — wrong suspect entirely

All three reveal the real verdict in the bot's response.
"""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

from agent.agents.detective.models import AccusationExtract, CaseRecord, Score


def score_accusation(extract: AccusationExtract, case: CaseRecord) -> Score:
    if not _name_matches(extract.name, case.accused_name):
        return Score.WRONG_PERSON
    if extract.verdict == case.verdict:
        return Score.CORRECT
    return Score.WRONG_VERDICT


def _ascii(s: str) -> str:
    """Normalize to lowercase ASCII, stripping diacritics (Müller → muller)."""
    return (
        unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower().strip()
    )


def _name_matches(player_name: str, accused_name: str) -> bool:
    a = _ascii(player_name)
    b = _ascii(accused_name)
    if a == b:
        return True
    # Substring: "muller" matches "franz muller"
    if a in b or b in a:
        return True
    # Last name only: player types "Muller" for "Franz Müller"
    parts = b.split()
    if parts and a == parts[-1]:
        return True
    # Fuzzy fallback for other typos
    return SequenceMatcher(None, a, b).ratio() > 0.75
