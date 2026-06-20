# User Stories

**Stage 3 — Operationalize success as user behavior.**

One line each: *As a `<user>`, I want `<to do X>` so that `<benefit>`.*

---

## Core investigation loop

| # | Story |
|---|-------|
| 1 | As a player, I want to receive a case briefing (accused, crime, setting) when a new case arrives so I understand what I'm investigating. |
| 2 | As a player, I want to see a list of evidence items so I know what the case file contains before I start asking. |
| 3 | As a player, I want to examine a named evidence item ("examine the railway ticket") so I can read what the record actually says about it. |
| 4 | As a player, I want to ask free-form questions about the case ("did the accused have an alibi?") so I can follow my own theory of the crime. |
| 5 | As a player, I want the game master to say "the record is silent on that" when my question has no answer in the transcript, so I trust I'm dealing with real facts. |
| 6 | As a player, I want a hint nudge when I've been inactive or am clearly stuck, so I don't abandon the case without resolution. |
| 7 | As a player, I want to make a formal accusation (/accuse) naming a suspect, so I get a clear resolution. |
| 8 | As a player, I want to see the real verdict and a brief of what actually happened, after I accuse, so I get the payoff. |
| 9 | As a player, I want my accusation scored (correct / wrong person / wrong verdict) so I know how well I read the evidence. |

## Player record & meta

| # | Story |
|---|-------|
| 10 | As a returning player, I want to see my detective record (/record): cases investigated, verdicts matched, accuracy rate. |
| 11 | As a returning player, I want a new case to arrive (a push message) after I close one, so the game keeps going without me having to ask. |
| 12 | As a player, I want to close a case without accusing (/close) so I'm not stuck forever if I give up — and I still get to see the real verdict. |

## Curation / admin (internal)

| # | Story |
|---|-------|
| 13 | As the curator, I want to run a script that fetches a case from Old Bailey Online and ingests it (brief, cast, evidence list, embedded transcript) into the database, so new cases can be added without rewriting code. |
| 14 | As the curator, I want the ingestion script to refuse a case without a verdict on record, so the game always has a resolution. |

---

## What "good" feels like

You get a message: "🔎 A new case has crossed your desk." The brief is gripping in three
sentences. You examine evidence, ask a question, get a real answer from the record. You make
your accusation. The reveal tells you what actually happened in 1845 — and whether you got it
right. It feels like being a detective, not like reading a Wikipedia article.

---

## Out of scope (for now)

- Multiple simultaneous active cases per player
- Multiplayer / cooperative mode
- Cases from sources other than Old Bailey Online (CourtListener, newspapers — later)
- Voice interface
- Generating images or scene descriptions with media.generate (later)
