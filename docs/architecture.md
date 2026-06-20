# Architecture

**Stage 5 — Break it into atomic modules.**

Each module does one thing and can be tested in isolation before it is composed into the full
bot. The composition happens in `bot.py` (stage 7).

---

## Module tree

```
src/agent/agents/detective/
├── models.py             — Pydantic types for the whole system (no I/O)
├── case_store.py         — DB: read cases and evidence items
├── chunk_store.py        — DB: store and search embedded transcript chunks (pgvector)
├── session_store.py      — DB: open / update / close player sessions
├── player_store.py       — DB: create and update player detective records
├── game_master.py        — LLM: answer player questions, strictly from retrieved chunks
├── accusation_extractor.py — LLM (fast): parse name + verdict from natural language
├── scorer.py             — Pure function: score accusation against real verdict
├── curator.py            — CLI script: ingest one case (fetch → LLM transform → embed → store)
├── bot.py                — Telegram bot wiring: handlers + Application (polling / webhook)
└── app.py                — FastAPI: webhook endpoint + /cron/nudge (production)
```

---

## Module table

| Module | Input | Output | Services used |
|--------|-------|--------|---------------|
| `models.py` | — | Pydantic types | — |
| `case_store.py` | `telegram_id`, `case_id`, `ref` | `CaseRecord`, `EvidenceItem` | db |
| `chunk_store.py` | `case_id`, texts, embeddings, `query_embedding` | `list[ChunkResult]` | db (pgvector) |
| `session_store.py` | `telegram_id`, session mutations | `Session`, `list[Session]` | db |
| `player_store.py` | `telegram_id`, score | `PlayerRecord` | db |
| `game_master.py` | `CaseRecord`, `list[ChunkResult]`, question | `str` | LLM (smart) |
| `accusation_extractor.py` | accusation text | `AccusationExtract \| None` | LLM (fast) |
| `scorer.py` | `AccusationExtract`, `CaseRecord` | `Score` | — |
| `curator.py` | transcript text file + slug | inserts to DB | LLM (smart), embed, db |
| `bot.py` | Telegram update | Telegram reply | all modules above |
| `app.py` | HTTP request | HTTP response | bot handlers |

---

## Data model

Table prefix: `detective_` (shared Neon DB, other projects use different prefixes).

### `detective_cases`

One row per curated historical case.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `serial PK` | |
| `slug` | `text UNIQUE` | e.g. `muller-1864` — deduplication key for curator |
| `title` | `text` | e.g. `THE PEOPLE v. FRANZ MÜLLER` |
| `court` | `text` | e.g. `Old Bailey` |
| `year` | `int` | Trial year |
| `accused_name` | `text` | Used for fuzzy-matching accusations |
| `crime` | `text` | Short description of the charge |
| `brief` | `text` | 3–4 sentence game opening |
| `cast_json` | `jsonb` | `[{name, role, description}, ...]` |
| `evidence_json` | `jsonb` | `[{id, label, summary}, ...]` |
| `verdict` | `text` | `guilty` or `not_guilty` |
| `verdict_text` | `text` | 1–2 sentences: what the jury decided and when |
| `aftermath_text` | `text` | 2–3 sentences: sentence, reaction, what followed |
| `active` | `bool` | False = excluded from the case pool |
| `created_at` | `timestamptz` | |

### `detective_chunks`

Overlapping chunks of each case's full trial transcript, with pgvector embeddings.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `serial PK` | |
| `case_id` | `int FK` | → `detective_cases` |
| `chunk_index` | `int` | Position in the transcript |
| `text` | `text` | ~400 words, 50-word overlap with neighbours |
| `embedding` | `vector(1024)` | baai/bge-m3 via OpenRouter |
| UNIQUE | `(case_id, chunk_index)` | |

HNSW index on `embedding` for fast cosine search (works well at small scale).

### `detective_sessions`

One row per player-case investigation (a player can replay a case but will get a new row).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `serial PK` | |
| `telegram_id` | `bigint` | Telegram user ID |
| `case_id` | `int FK` | → `detective_cases` |
| `status` | `text` | `active` / `solved` / `abandoned` |
| `clues_examined` | `jsonb` | `["e1", "e3", ...]` — evidence IDs examined so far |
| `hint_count` | `int` | Hints used; max 3 per session |
| `pending_accusation` | `bool` | True while waiting for accusation text from player |
| `accusation_name` | `text\|null` | What the player said at /accuse |
| `accusation_verdict` | `text\|null` | `guilty` or `not_guilty` |
| `score` | `text\|null` | `correct` / `wrong_verdict` / `wrong_person` |
| `started_at` | `timestamptz` | |
| `last_active_at` | `timestamptz` | Updated on every player action; used for nudge cron |
| `closed_at` | `timestamptz\|null` | |

### `detective_players`

Lifetime detective record per Telegram user.

| Column | Type | Notes |
|--------|------|-------|
| `telegram_id` | `bigint PK` | |
| `cases_attempted` | `int` | Incremented on close (any outcome) |
| `cases_correct` | `int` | Right person + right verdict |
| `cases_wrong_verdict` | `int` | Right person, wrong verdict |
| `cases_wrong_person` | `int` | Wrong suspect |
| `cases_abandoned` | `int` | Closed without accusing |
| `created_at` | `timestamptz` | |
| `last_active_at` | `timestamptz` | |

---

## Data flow diagrams

### 1. Player asks a free-form question

```
Player text
  → bot.handle_message()
  → session_store.get_active_session()   [DB read]
  → llm.embed_one(question)             [embedding API]
  → chunk_store.search_chunks(k=5)      [pgvector cosine search]
  → game_master.answer_question()       [LLM "smart" tier, chunks as context]
  → update.message.reply_text()
  → session_store.touch_session()       [DB write: last_active_at]
```

### 2. Player makes a formal accusation

```
Player: /accuse
  → bot.handle_accuse()
  → session_store.set_pending_accusation(True)
  → reply: "State your accusation..."

Player: "Franz Müller, guilty"
  → bot.handle_message()
  → session_store.get_active_session()  [pending_accusation = True]
  → accusation_extractor.extract()      [LLM "fast": name + verdict]
  → scorer.score_accusation()           [pure: fuzzy name match + verdict compare]
  → session_store.close_session()       [DB write: score, status=solved]
  → player_store.record_outcome()       [DB write: update detective record]
  → reply: reveal message
  → case_store.get_next_case()          [DB read: next unplayed case]
  → session_store.open_session()        [DB write: new session]
  → reply: new case brief
```

### 3. Case ingestion (curator script)

```
uv run detective-ingest --file transcript.txt --slug muller-1864
  → read transcript text from file
  → LLM ("smart"): transform_case()    [extract title, cast, evidence, verdict, brief]
  → assert verdict present              [hard gate: no verdict = abort]
  → chunk_text()                        [~400 words, 50-word overlap]
  → llm.embed(chunks)                   [batch embedding: baai/bge-m3]
  → db INSERT detective_cases           [structured case data]
  → chunk_store.store_chunks()          [INSERT detective_chunks with embeddings]
```

### 4. Inactivity nudge (cron)

```
Railway Cron (hourly) → POST /cron/nudge
  → session_store.get_stale_sessions(threshold_hours=24)
  → for each stale session:
      → case_store.get_evidence_item()  [pick unexamined evidence]
      → llm.embed_one(focus item)
      → chunk_store.search_chunks()
      → game_master.generate_hint()    [LLM: hint from retrieved chunks]
      → telegram bot.send_message()
      → session_store.increment_hint_count()
```

---

## Grounding: how the LLM stays truthful

This is the critical constraint: the game master must only answer from the trial record.

1. At ingest time, the full transcript is chunked (~400 words with 50-word overlap) and each
   chunk is embedded and stored in pgvector.

2. At query time, the player's question is embedded and the top-5 most similar chunks are
   retrieved via cosine similarity.

3. The game master's system prompt is explicit:
   - Answer **only** from the retrieved passages
   - If no relevant passage found → "The record is silent on that, Detective."
   - **Never** draw on training knowledge about this case
   - **Never** reveal the verdict before /accuse

4. The 50-word overlap between chunks prevents a relevant passage from being split across a
   chunk boundary and becoming unsearchable.

5. Top-5 retrieval (not top-1) handles phrasing mismatches: Victorian "the prisoner proceeded
   to" vs. player's "did he walk to".

---

## Key technical decisions

**No ConversationHandler** — Unlike the protein bot, there's no multi-step onboarding wizard.
All game state is in the DB (`detective_sessions`). Every message handler reads the session and
acts on its state. Simpler, survives restarts.

**`pending_accusation` in DB, not `context.user_data`** — Storing the "awaiting accusation"
flag in the session table means it survives bot restarts. The user doesn't lose their accusation
flow if the bot redeploys mid-game.

**HNSW over IVFFlat** — IVFFlat needs a minimum row count (~100/cluster) for a good index.
With 5–10 cases × ~50 chunks each = 250–500 total chunks, HNSW is the right choice: it works
well at small scale and degrades gracefully.

**Smart tier for game master, fast tier for extraction** — Faithfulness to retrieved text
requires the best available model. Accusation extraction is a simple structured task that fast
models handle well. This keeps per-game costs reasonable.

**Slug-based deduplication in curator** — The `slug` column is UNIQUE. Running the curator
twice with the same slug does nothing (`ON CONFLICT DO NOTHING`), making ingest idempotent.

**Fuzzy name matching in scorer** — Players type "Müller" not "Franz Müller"; "Adelaide" not
"Adelaide Bartlett". `difflib.SequenceMatcher` + last-name substring match handles common
variants without needing an NLP library.

**Separate environments, separate bot tokens** — Same pattern as protein bot and
inspiration_bot. Local = polling; Railway = webhook. Two consumers on one token = Telegram 409.
