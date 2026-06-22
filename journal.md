# Journal

This is the running trace of your thinking as you build. It's the most important
document in the project — more than any single piece of code.

**How to use it**
- Add an entry at *meaningful* moments: a decision (and **why**), something you
  learned, a dead end you backed out of, a milestone reached.
- **Not** every edit. Capture the thinking, not the keystrokes.
- Always **timestamp** with date **and** time. Newest entries go at the bottom.
- Both you and Claude should add entries.

Format:

```
## YYYY-MM-DD HH:MM — Short title
What you were trying to do, what you decided, and why. What you learned.
```

---

## 2026-05-29 12:00 — Project initialized from the agent starter
Cloned the starter. Next: fill in `docs/problem.md` (what can't I do today?) and the
"Your project" section of `README.md` (what am I building?). Then design before coding.

## 2026-06-07 — Chose project and designed the foundation: protein-tracking Telegram bot

**The project:** A Telegram bot that helps Caroline track protein intake via food photos.

**The problem (stage 1):** Caroline needs to eat more protein due to age, but doesn't know
which foods are high in protein or whether she's gotten enough during the day. She wants
easy logging, daily feedback, and a timely nudge if she's falling behind.

**Decisions made:**

- **Interface:** Telegram bot. Photo → logged, no forms. Chosen because friction must be
  minimal — otherwise people don't log.

- **Protein goal:** The agent calculates a personal goal based on age, weight, height, and
  sex (not a fixed default). Rationale: an accurate goal requires personal data.

- **Reminder:** At 15:00 every day. If Caroline is under her goal → reminder with how much
  is missing. If she's already hit her goal → positive confirmation instead.

- **Learning from corrections:** If the agent guesses the wrong protein amount, Caroline can
  correct it ("no, it was 28g"). The correction is saved in the database and prioritized the
  next time the same food appears. The agent always confirms the correction before saving.

- **Estimates are always approximate:** The agent should never give confidently exact numbers.
  "About 25–35g" is the right format, not "31.4g".

**User stories done (6):** photo logging, daily status, 15:00 reminder, weekly summary,
ask about protein content, correct and learn.

**Failure modes identified:** unclear photo, mixed dish, wrong guess, forgotten logging,
non-food photo, goal already reached, network error, wrong correction.

**Protein goal — onboarding questions (beyond age, weight, height, sex):**
Activity level and goal are the most important variables (can shift the target by 50–100%).
Diet style affects bioavailability of plant proteins.
Pregnancy/breastfeeding question is only asked of users who specified sex = female.
Medical conditions (e.g. kidney disease) are not handled — the agent refers to a doctor.

Full onboarding sequence:
1. Age, weight, height, sex (female / male / other or prefer not to say)
2. Activity level (sedentary / moderately active / exercises regularly / trains hard)
3. Goal (maintain muscle / lose weight / build muscle)
4. Diet style (omnivore / vegetarian / vegan)
5. (Everyone except "male") Pregnant or breastfeeding? (yes / no)

Sex "other / prefer not to say" → protein goal calculated as average of female and male
formulas.

**The 15:00 reminder asks about dinner plans (option 1):**
If protein is missing, the agent asks "Are you planning dinner tonight?" before suggesting a
snack. Otherwise the user risks eating both a snack and dinner and overshooting the goal.
Option 2 (learns from history) can be added later once data exists.

**Ingredient calculation + recipe memory:**
For home-cooked food (stew, soup, etc.) the agent asks for ingredients, quantities, and
number of servings and calculates protein per portion. Saves the recipe if the user wants —
reused next time the same dish is logged. Tied to the correction-learning feature.

**Next step:** Scenarios (stage 3) — concrete walkthroughs with real example inputs.

## 2026-06-07 — Wrote scenarios, failure modes, and policy (stages 3–4)

**Scenarios** (`docs/scenarios.md`) — 8 concrete end-to-end walkthroughs:
- Happy paths: simple food photo, home-cooked food with ingredients, status check on demand,
  15:00 reminder with deficit, 15:00 reminder with goal already reached.
- Edge cases: blurry photo, non-food photo, wrong guess → correction and learning.

Key decisions in scenarios:
- Status is triggered by natural language ("status", "how am I doing?", "what's left?"),
  not only by an exact command — bot must understand intent.
- Every food-log reply always shows the running daily total, unprompted.
- 15:00 reminder asks about dinner plans before suggesting snacks to avoid overshooting.
- Correction is always confirmed before it is saved.

**Failure modes** (`docs/failure_modes.md`) — 13 failure cases documented:
- Each has likelihood, severity, and how the agent handles it gracefully.
- Hard rules: never a single precise protein number, never log from an unidentifiable photo,
  never save a correction without confirmation, never handle medical questions.
- User-facing error messages are always short, honest, and give a clear next step.

**Policy** (`docs/policy.md`) — 5 step-by-step flows:
onboarding, food photo, status request, correction, 15:00 reminder.
- Suggestion engine added to the 15:00 flow: concrete dinner ideas with protein estimates,
  snack only if the deficit is likely to remain after dinner.
- Tool table clarifies which service each module uses.
- Tone rules: concise, warm, never preachy, always approximate ranges.

## 2026-06-07 — Built the full codebase (stage 5–6 start)

**Architecture** (`docs/architecture.md`) — 12 atomic modules designed, three DB tables,
three data flow diagrams (photo, text, scheduler). Decided not to use R2 or fal.ai —
photos are analysed in-flight via vision LLM and don't need to be stored.

**Code built** (`src/agent/agents/proteinbot/`):

- `models.py` — Pydantic models + StrEnum for all domain types.
- `goal_calculator.py` — protein goal formula: base g/kg by activity, age bump at 40+/50+,
  goal multiplier, sex multiplier, +25g for pregnancy, +10g buffer for vegan diet.
- `food_analyzer.py` — pydantic-ai Agent with vision model (balanced tier = claude-sonnet),
  returns structured `FoodEstimate` with is_food, is_identifiable, is_home_cooked flags.
- `ingredient_calculator.py` — LLM parses free-text ingredient list + portions → protein
  per portion range. Uses "fast" tier since it's straightforward arithmetic.
- `intent_classifier.py` — classifies text as status / correction / off_topic; also
  extracts corrected gram value for corrections. Fast-tier LLM + heuristic shortcut.
- `suggestion_engine.py` — generates dinner or snack suggestions respecting diet style.
- `meal_logger.py`, `daily_tracker.py`, `correction_handler.py`, `recipe_store.py` —
  DB read/write modules, each doing exactly one thing.
- `bot.py` — Telegram bot wiring: ConversationHandler for onboarding (8 states),
  photo handler, text handler (state machine via user_data), dinner callback,
  daily 15:00 JobQueue reminder. Uses PTB v22 `post_init` hook for migrations.

**Key technical decisions:**
- `_ud(context)` helper asserts `context.user_data is not None` once, keeping all
  handlers clean without repeated guards.
- `run_polling()` is called synchronously from `main()` — PTB v20+ manages its own
  event loop; wrapping it in `asyncio.run()` caused a type error.
- Migrations run via PTB's `post_init` hook, not a separate `asyncio.run()` call,
  to avoid nested event loop issues.
- 15:00 reminder uses inline keyboard buttons (dinner_yes / dinner_no) rather than
  waiting for free text, so the dinner callback is unambiguous regardless of what the
  user types next.

**Status:** ruff clean, pyright 0 errors. Ready to wire up credentials and run live.

## 2026-06-07 — Added custom protein goal override

Users now get a suggested goal at the end of onboarding but can override it. The flow:
1. Agent calculates suggested goal and shows it with two buttons: "Use Xg" / "Set my own".
2. If "Set my own": bot asks for a number (validated 10–500g) and saves that instead.

Added two new ConversationHandler states: `OB_CONFIRM_GOAL` and `OB_CUSTOM_GOAL`.
The suggested goal is stored temporarily in `KEY_PROFILE_DRAFT["_profile_json"]` as a
serialised UserProfile so `ob_confirm_goal` can save it without recalculating.

Policy and scenarios updated to reflect this.

## 2026-06-07 — Added perimenopause/menopause question for women 40+

Oestrogen drop during peri/menopause accelerates muscle loss and raises protein needs.
Added +15g/day to the goal for users who answer yes.

Changes:
- `migrations/002_proteinbot_menopause.sql` — adds `perimenopausal bool` column.
- `models.py` — `perimenopausal: bool | None` added to `UserProfile`.
- `goal_calculator.py` — +15g if `perimenopausal` is True.
- `bot.py` — new state `OB_MENOPAUSE`; question triggers only for `sex == "female"` AND
  `age >= 40` AND `not pregnant`. Males and "other" skip it. Pregnant women skip it too
  (pregnancy and menopause are mutually exclusive in practice).

## 2026-06-07 — Added /reset command for testing

`/reset` deletes all meals, recipes, and the user profile from the database and clears
`context.user_data`. Makes it possible to re-run onboarding without touching the DB manually.
This is a dev/test tool — worth removing or gating before any public release.

## 2026-06-08 — Debugged two bugs found during live testing

**Bug 1: Menopause question not appearing.**
Added `logger.debug()` to `ob_pregnant` to log `pregnant`, `sex`, and `age` at runtime.
Root cause not yet confirmed from logs (user ran reset and restarted before logs were captured),
but the question works after the second bug was fixed.

**Bug 2: Bot looped back to "Type /start to set up your profile first" after typing age.**
Root cause: multiple bot instances were running simultaneously. Each previous call to
`uv run proteinbot` in the chat started a new background process without stopping the old one.
Conversation state is stored in memory per process — one instance handled `/start` and set
state to `OB_AGE`, a different instance received the age text and had no state for that user,
so it fell through to `handle_text` which returned the /start prompt.

Fix: `pkill -f proteinbot && uv run proteinbot` to kill all instances and start exactly one.
Lesson: always kill the old bot before starting a new one during local testing.

## 2026-06-08 — Added contextual meal feedback and on-demand meal suggestions

**Feature 1: Contextual feedback after every logged meal.**
After logging any meal (photo or home-cooked), the bot now comments on whether the
protein amount is appropriate for the time of day relative to the daily goal.

Implementation: `suggestion_engine.feedback_after_meal()` takes meal protein, daily total,
goal, diet style, and current hour. A time-based lookup table maps hours to expected
cumulative fractions of the daily goal (e.g. by 9am ~20% expected, by 1pm ~50%). The
distance between actual and expected determines the tone: on track, a bit low, or great
start. If low, 1–2 concrete food additions are suggested. Uses "fast" tier LLM.

**Feature 2: Meal suggestions on demand.**
The user can ask "what should I eat for lunch?" or "middag förslag?" and the bot responds
with 2–3 concrete suggestions calibrated to the remaining daily deficit.

Implementation: added `meal_suggestion` as a fourth intent in `intent_classifier`, with
`meal_type` extracted (e.g. "lunch", "dinner"). `suggestion_engine.suggest_for_meal()`
takes the meal name, remaining grams, and diet style. If the goal is already reached, the
bot says so and offers suggestions as inspiration only.

**Docs updated:** policy.md, scenarios.md, architecture.md, failure_modes.md all synced
to reflect the two new features, the perimenopause question, and the custom goal flow.

## 2026-06-08 — Multilingual input + activity level UX fix

**Multilingual input:**
Decision: bot responds in English but understands input in any language.
Responding in the user's language was considered but rejected for now — it would require
detecting and storing a per-user language, passing it through every LLM call, and generating
all fixed strings dynamically. The complexity isn't worth it until there are non-Swedish users.

What was changed:
- `intent_classifier`: system prompt explicitly states "messages may be in any language",
  with examples in French and German. `is_status_request` heuristic expanded with FR/DE/ES
  keywords to avoid unnecessary LLM round-trips for obvious status queries.
- `ingredient_calculator`: system prompt says "ingredient lists may be in any language"
  and "write the description in English" — so stored meal descriptions are always consistent.
- `bot.py` yes/no detection: expanded from `(yes, ja, y)` / `(no, nej, n)` to cover
  `oui, si, da, tak, yep, sure, ok` and `non, nein, nie, nope, cancel`.

**Activity level keyboard UX fix:**
The inline keyboard had 4 buttons in a single row. On mobile Telegram, each button got ~25%
of screen width, cutting labels to the first word ("Mostly", "Moderately", "Exercise").

Fix: switched to a 2×2 grid using a new `_keyboard_rows()` helper, and shortened labels to
one descriptive word each: Sedentary / Moderate / Active / Intense. Added a description of
each level in the message text above the buttons so the user knows what each means without
needing long button labels.

## 2026-06-08 — Fixed three failure modes + deployed to Railway

**Failure mode #3 — Correction only worked on the last meal:**
When 2+ meals were logged today, the bot always corrected the most recent one regardless
of what the user intended. Fixed by showing an inline keyboard listing all of today's meals
when there are 2 or more. The user picks which meal to correct, then provides the actual
grams. If there's only one meal, the keyboard is skipped and correction proceeds directly.
New callback handler: `handle_meal_correction_callback` (pattern `^corr_meal_\d+`).

**Failure mode #4 — Recipe suggestions not connected to saved recipes:**
The suggestion engine had no knowledge of the user's saved recipes, so it couldn't suggest
them. Fixed by adding `list_recipes()` to `recipe_store.py` and passing `saved_recipe_names`
into all four suggestion engine functions. The system prompt now mentions saved recipes and
asks the LLM to consider them when relevant.

**Failure mode #6 — Daily reminder fired at wrong local time for non-CET users:**
The reminder ran as a daily job at a fixed UTC time, which is wrong for users in other
timezones. Fixed by:
- Adding `timezone_offset: int = 1` to `UserProfile` (default UTC+1 / CET).
- Adding a `/timezone` command with a 3×3 inline keyboard covering UTC-8 to UTC+10.
- Switching the reminder job from `run_daily` to `run_repeating(interval=3600)` — it now
  fires every hour and only sends a message if the user's local hour is 15:00.
- Adding `last_reminded_date` (date column) to the DB to prevent double-sends on restart.
- Migration: `003_proteinbot_timezone.sql` adds both new columns.

**Deployment to Railway:**
Goal: bot runs 24/7 without the laptop open.

Lessons from a difficult deploy:
- Railway free plan hit resource limit mid-session — had to upgrade to Hobby (~$5/mo).
- `railway init` kept timing out silently while creating empty projects; ended up with 4
  duplicate "proteinbot" projects. Cleaned up by deleting them via dashboard Settings →
  Delete project. Future approach: create the service via dashboard first, then `railway link`.
- Secrets must be set via `railway variables --set "KEY=VALUE"` — `.env` is gitignored and
  not in the Docker image. Never commit secrets.
- Don't put `$PORT` in `startCommand` — Railway runs without a shell so vars don't expand.
  A polling bot has no inbound HTTP, so `$PORT` isn't needed at all.
- `telegram.error.Conflict` crash loop: Railway restarts on crash, new instance conflicts
  with dying old one, crash, repeat. Root cause turned out to be a duplicate Railway service
  with the same bot token running in a different project. Fixed by deleting the duplicate
  project. Also added `drop_pending_updates=True` to `run_polling()` so the bot clears
  stale updates on every fresh start, making restarts more resilient.

## 2026-06-09 19:50 — Fixed password re-prompt for existing users after adding auth gate

After adding the password gate (migration 004 + `proteinbot_authorized` table), users who
already had a profile were being asked for the password again when uploading food photos.

Root cause: `_is_authorized` only looked at `proteinbot_authorized`. If the migration
backfill (`INSERT INTO proteinbot_authorized SELECT telegram_id FROM proteinbot_users`)
didn't catch an existing user — e.g. due to Railway deployment timing or env var sequencing
— they'd be treated as unauthorized on every request despite having a completed profile.

Fix: `_is_authorized` now falls back to checking `proteinbot_users`. Anyone with a completed
profile is implicitly authorized and gets auto-backfilled into `proteinbot_authorized` on
their next interaction, so future checks are instant.

Lesson: when adding an access gate to an existing system, the "grandfather existing users"
step is critical but fragile. Even with a migration backfill, a defensive fallback in the
auth check is worth the extra query.

## 2026-06-15 — Added example #3: inspiration_bot (Telegram, both-directions agent)
Built the third worked example as a Telegram bot, deliberately keeping the repo single-spirit
(pure Python toolbox) instead of going React/Next + Better Auth — that's a separate starter,
not this one. Telegram dissolves the "auth" question: identity is the verified `telegram_id`
on every update; the users table is keyed on it; authorization is a thin optional allowlist.

Key decisions:
- **Environments as a first-class concept.** Added `ENVIRONMENT` (+ telegram/cron settings) to
  config.py. Same code, different *values* in `.env` vs Railway. Separate bot token per env is
  mandatory, not hygiene: two consumers on one token = Telegram 409. This is the example's spine.
- **Webhook vs polling, chosen by environment.** Local = long polling (no public URL); prod =
  webhook into a FastAPI app that also hosts the cron endpoint. One codebase.
- **Cron = frequent tick + per-user due-check.** Railway Cron (hourly) → `run_due_sends`, which
  honours each user's hour/timezone/cadence and is idempotent via `last_sent_at`. `is_due` is a
  pure function, unit-tested offline. Same `cron` command forces an immediate send in dev.
- **Tool-using agent with injected scope.** pydantic-ai `Deps(telegram_id)` is injected, never a
  tool argument — so the model physically can't reach another user's data. Read tools granted
  freely; one reversible write tool (set_schedule); delete + image-gen kept out of the model's
  hands (human-confirmed / orchestrated). This is the security lesson I most want to land.
- **Packaging:** multi-file example as a package (`examples/__init__.py` + the bot's `__init__.py`),
  so absolute imports work under both `python -m ...` and `fastapi run ...` (verified how
  fastapi-cli walks `__init__.py` parents). Added `pythonpath=["."]` so pytest can import it.

Verified the installed APIs before writing (pydantic-ai 1.104 deps/tools/BinaryContent; PTB 22.8
Application/handlers/webhook) rather than trusting memory. ruff + pyright clean; 9 offline tests.

## 2026-06-20 11:00 — Started The True-Crime Detective; defined the project

**What we're building:** A single-player detective game backed by real historical court records,
delivered as a Telegram bot. The player investigates genuine cases — Old Bailey, Victorian era —
examines evidence, questions the record in natural language, makes a formal accusation, and learns
what actually happened. The tagline: *Causae verae ex archivo* — real causes from the archive.

**Why this project:** Historical court transcripts are extraordinary primary sources — vivid, factual,
often shocking — but the reading experience kills the drama. A 200-page Old Bailey transcript dumps
you into dense 19th-century legalese with no guide, no structure, no game. The AI doesn't add
invention; it adds mediation. It turns an archive into an investigation.

**The unique constraint that shapes everything:** This is not a fictional mystery. The facts must be
real. A confident hallucination doesn't just break the game — it's a lie. This makes grounding the
single most important engineering challenge, not an afterthought.

**Case source chosen:** Old Bailey Online (oldbaileyonline.org). It covers London criminal courts
1674–1913 and has a proper API. Victorian-era cases (1800–1913) are the sweet spot: richest
transcripts, most familiar cultural setting, still public domain. Will start with 5–10 hand-picked
cases — murder, poisoning, forgery — before considering other sources (CourtListener for US federal
cases, historical newspapers) as a later extension.

## 2026-06-20 11:30 — Chose Telegram bot as the interface

**Decision:** Telegram bot. The other options were a web app and a CLI.

**Why Telegram:** Investigation naturally benefits from async — you examine the evidence, think, come
back. Telegram supports that; a web page implies you'll sit there. We also already have Telegram
infrastructure patterns in this repo (protein bot, inspiration_bot), so the deployment path is known.

**Why not web:** The "case file desk" aesthetic would be compelling, but the layout benefit doesn't
outweigh the extra complexity right now. Web is the obvious next step if the Telegram version works
and feels cramped. We want one complete path end-to-end first.

**Why not CLI:** Fast to build but dead-ends immediately — no push delivery, no async, no deployment.

## 2026-06-20 12:00 — Decided on pre-ingest as the data strategy

**Decision:** Pre-ingest. We curate cases by hand, transform each into structured data (brief, cast,
evidence list, verdict, chunked + embedded transcript), and store everything in Neon. Gameplay runs
entirely from the local database — no live API dependency during play.

**The two paths considered:**
- *Pre-ingest:* Smaller pool, upfront curation work, but reliable, consistent quality, fast gameplay.
  Adding a case = running the curator script once.
- *Live retrieval:* Query the Old Bailey API in real-time, transform on the fly. Unlimited pool, but
  more complexity, latency risk, variable case quality, and live API dependency during play.

**Why pre-ingest wins now:** We need one complete, trustworthy path end-to-end. The fun isn't in the
volume of cases; it's in the quality of one well-curated investigation. Live retrieval is a later
extension (Stage 2 of the data strategy), not a day-one requirement. We'll note this clearly in the
architecture so it doesn't feel like a permanent limitation.

**Case pipeline (what pre-ingest means in practice):**
1. Curator runs a script: fetch raw XML transcript from Old Bailey Online API
2. LLM extracts structured data: case brief (3–4 sentences), cast of characters, evidence list with
   labels and summaries, real verdict text
3. Full transcript is chunked (~500 tokens per chunk, with overlap)
4. Each chunk is embedded (1024-dim via embed() from llm.py) and stored in pgvector
5. All of it goes into Neon: `detective_cases` + `detective_chunks` tables
6. Script refuses to add a case without a verdict on record (hard gate)

## 2026-06-20 12:30 — Designed the grounding approach

**The problem:** The LLM game master must never invent facts about the case. Famous Victorian
murders are well-known to LLMs from training data — if we're not careful, the model will answer
from memory instead of the record and might even be right, but the *game* demands it answer from
the *record*. We can't verify memory vs. record at runtime.

**The solution — strict RAG:**
- Every player query (free-form question or evidence examination) triggers a cosine similarity
  search over the embedded transcript chunks
- Top-5 chunks are retrieved and passed to the game master LLM as its sole context
- System prompt is explicit: "Answer ONLY from the passages below. Never use training knowledge
  about this case. If the answer is not in these passages, say: 'The record is silent on that.'"
- The LLM is instructed to quote the record directly rather than paraphrase

**The "record is silent on that" rule is a feature, not a bug.** Real archives have gaps. A player
asking "what was the defendant's childhood like?" getting "the record is silent on that" is accurate,
honest, and teaches something real about historical evidence.

**What can go wrong with retrieval:** Embedding-based retrieval can miss a relevant chunk if the
player's phrasing doesn't match the transcript's phrasing (a Victorian witness says "the prisoner
proceeded to" while the player asks "did he walk to"). Mitigation: top-k = 5, not 1; and the system
prompt asks the LLM to say "I can't find that in the record — try asking differently?" rather than
silently wrong.

## 2026-06-20 13:00 — Designed the game loop, scoring, and inactivity mechanics

**Game loop:**
1. New case is pushed to the player (cron or after closing the previous case)
2. Player examines evidence items by number or name, asks free-form questions
3. When ready: /accuse → state a name and verdict (Guilty / Not Guilty)
4. Reveal: real verdict + explanation, score, next case offered
5. Player can /close at any time to see the verdict without accusing (no score)

**Scoring:** Three levels — the reveal always shows the real verdict regardless of score.
- ✅ Correct: name matches accused AND verdict matches real verdict
- ⚠️ Wrong verdict: name matches but verdict is wrong (e.g. player said Guilty but real verdict Not Guilty)
- ❌ Wrong person: name doesn't match (or player accused the victim)

**Why wrong verdict is a separate tier:** Some of the most interesting Old Bailey cases are acquittals
that shocked contemporaries (Adelaide Bartlett, 1886). A player who identified the right person but
guessed Guilty deserves to know they read the evidence correctly even if they misjudged the jury.

**Inactivity nudge:**
- Cron checks sessions inactive for >24 hours
- Sends a hint drawn from a transcript chunk related to key unexamined evidence
- Maximum 3 hints per case — after the third, offers /close
- Hints never name the culprit; they point to evidence and let the player draw conclusions

**Commands designed:** /examine N, /ask (or just type), /accuse, /hint, /close, /record, /newcase

## 2026-06-20 13:30 — Completed stages 1–4 docs

**Files written (all replacing protein-bot content):**

- `docs/problem.md` — the archive access problem; why grounding is the central challenge
- `docs/user_stories.md` — 14 stories: 9 for the core loop, 3 for player record/meta,
  2 for curator tooling. Out of scope noted: multiplayer, other sources (for now), voice
- `docs/failure_modes.md` — 13 failure modes. Most important: LLM hallucination (RAG solution);
  player asking for verdict early (in-character refusal); ambiguous real verdicts (this is a feature);
  prompt injection attempts ("ignore previous instructions" → treated as an in-game question)
- `docs/scenarios.md` — 8 walkthroughs using real cases: Franz Müller (1864) and Adelaide
  Bartlett (1886). Covers happy paths (new case, examine evidence, free-form Q&A, accusation,
  hint) and edge cases (question with no answer, asking for verdict early, wrong-person accusation,
  all cases completed)
- `docs/policy.md` — 7 flows (case delivery, examine, free-form Q, hint, accusation, close, record);
  tools table; tone rules (formal, measured, Victorian register); 6 hard rules
- `README.md` — "Your project" section now describes The True-Crime Detective

**Tone decision recorded in policy:** The game master speaks in a formal, measured, evocative
register — "the record shows", "the testimony of X states". Never chatty, never preachy, never
moral commentary on the era's justice system unless the player explicitly asks. Quotes over
summaries: when a passage answers the question, reproduce it rather than paraphrase it.

**Next:** `docs/architecture.md` (stage 5) — modules, DB schema, data flow diagrams. Then code.

## 2026-06-20 14:00 — Built architecture (stage 5): docs, migrations, all 11 modules

**Architecture doc written** (`docs/architecture.md`): module table, full DB schema (4 tables),
3 data flow diagrams (question, accusation, ingest), key technical decisions explained.

**4 migrations written** (migrations/005–008):
- `005_detective_cases.sql` — case metadata, cast_json, evidence_json, verdict, brief
- `006_detective_chunks.sql` — pgvector chunks with HNSW index (better than IVFFlat at small scale)
- `007_detective_sessions.sql` — per-player-per-case state; pending_accusation flag in DB (survives restarts)
- `008_detective_players.sql` — lifetime detective record

**11 modules written** (`src/agent/agents/detective/`):
- `models.py` — Pydantic types: Verdict, Score, SessionStatus, CaseRecord, Session, etc.
- `case_store.py` — get_next_case (excludes played cases), get_case, get_evidence_item (by index or label)
- `chunk_store.py` — store_chunks (bulk insert, idempotent), search_chunks (pgvector cosine)
- `session_store.py` — full lifecycle: open, examine, hint, accuse, close, stale detection
- `player_store.py` — upsert on every touch; record_outcome increments the right counter by name
- `game_master.py` — pydantic-ai Agent (smart tier); chunks passed in message, not as deps
- `accusation_extractor.py` — fast-tier Agent with AccusationExtract output type
- `scorer.py` — pure function: exact match, substring, last-name, then difflib fuzzy (ratio > 0.75)
- `curator.py` — CLI: reads transcript, LLM transforms, chunks+embeds, stores; dry-run flag
- `bot.py` — all handlers, no ConversationHandler; state machine driven by DB session
- `app.py` — FastAPI webhook + /cron/nudge endpoint for production (same pattern as inspiration_bot)

**pyproject.toml updated**: `detective` (polling) and `detective-ingest` script entries added.

**ruff clean, pyright 0 errors.**

**Key decisions made during implementation:**

- `pending_accusation` stored in DB (not context.user_data) so accusation flow survives bot restarts.
  Simple: if session.pending_accusation is True, next text message is treated as the accusation.

- `_case_brief_text()` and `_next_case_text()` separated cleanly. No context threading required.

- Curator's file reading moved to `main()` (synchronous) rather than inside `async def ingest()`,
  to satisfy ruff's ASYNC240 rule (no blocking Path.read_text inside async functions).

- `strict=True` added to zip() in chunk_store — texts and embeddings must match 1:1; if embed()
  returns a different count, we want an immediate error, not silent data corruption.

- jsonb writes in curator use `json.dumps() + ::jsonb` cast (explicit and safe with asyncpg).
  Session clues_examined also uses json.dumps() for the same reason.

**Next: Stage 6** — test each module in isolation (`scripts/tests/`), starting with
scorer (pure, no deps) and game_master (mock chunks to verify grounding prompt).

## 2026-06-20 15:30 — Stage 6 complete: tests written, real bug found and fixed

Wrote `scripts/tests/test_detective.py` — 28 offline tests, 4 integration tests (live LLM, skipped without credentials).

**Coverage across modules (all offline):**
- **scorer**: 8 tests — exact/partial/surname/case-insensitive name matching, CORRECT/WRONG_VERDICT/WRONG_PERSON outcomes, accusing the victim
- **models**: 5 tests — enum values, CaseRecord construction, AccusationExtract validation
- **chunk_store._vec**: 2 tests — pgvector literal formatting
- **curator._chunk_text**: 5 tests — empty/short/overlap/count/no-empty-chunks
- **bot helpers**: 4 tests — _pct edge cases, _SCORE_LINES coverage guard
- **game_master (mock)**: 3 tests — chunk text in prompt, examined list in hint prompt, empty-chunks message
- **accusation_extractor (mock)**: 1 test — returns None on exception

**Bug found by testing:** `scorer._name_matches()` failed on "Muller" vs "Franz Müller".
SequenceMatcher ratio was ~0.56, below the 0.75 threshold. The substring and last-name checks
also failed because they compared against the un-normalized string. Players WILL type names without
umlauts — this would have been a silent wrong-person result for one of our primary example cases.

**Fix:** Added `_ascii()` normalizer in scorer — strips diacritics via NFKD + ASCII encode before
any comparison. Now "Muller" → ascii → "muller", "Franz Müller" → "franz muller",
and the substring check "muller" in "franz muller" catches it.

This is exactly why we test atomic modules before composing them.

**Integration tests written (live LLM):**
- Accusation extractor: guilty and not-guilty paths with real inputs
- Game master: grounding check (invented chunk fact should appear in answer), silent check (off-topic chunk → hedged response)

All 44 tests pass. ruff clean. pyright 0 errors.

**What's next (Stage 7):** The code is all there. Next real step is to ingest an actual Old Bailey
transcript (`uv run detective-ingest --file transcript.txt --slug <slug>`) and run the bot
locally (`uv run detective`) to test the game end-to-end. Then deploy to Railway.

## 2026-06-20 17:00 — Ingested Franz Müller (1864) — first real case live

Got the actual Old Bailey Online transcript for Franz Müller (t18641024, ~29,500 words).
The LLM extraction (smart tier) produced excellent structured data: gripping brief,
8 cast members including Detective Tanner who chased Müller to New York, 8 evidence items
covering the watch, chain, cut-down hat, and bloodstained carriage No. 69. Aftermath
mentions "Müller's lights" — the real historical consequence (viewing apertures added to
railway carriages). 85 chunks embedded and stored to pgvector.

## 2026-06-20 18:00 — Ingested Adelaide Bartlett (1886) — second case, NOT GUILTY verdict

56,000-word transcript, nearly twice the Müller case. The LLM found the central riddle
precisely: "how could a fatal dose of fiery, burning chloroform have reached a man's
stomach without leaving a single trace?" George Dyson (the minister) appears as co-accused.
161 chunks. Verdict: not_guilty — players who are certain she did it get WRONG_VERDICT, not
WRONG_PERSON. The Sir James Paget quote made it into the aftermath_text.

## 2026-06-20 22:00 — Several bugs found and fixed during live play

**jsonb decoding bug (hit twice):** asyncpg's type-codec registration via `init=_init_conn`
isn't reliable through Neon's pgbouncer proxy. Fixed with a defensive `_j()` helper in
`case_store._row_to_case` and `session_store._row_to_session` that calls `json.loads()` if
the value is a string. The `db.py` init callback is kept as a best-effort layer.

**Accusation flow UX:** after accusing, the verdict reveal and the next case dropped as two
consecutive messages — no time to read. Fixed: removed `_next_case_text` from the reveal
flow entirely. Now the reveal ends with "When you're ready: /newcase". Players advance on
their own terms.

**Evidence UX:** `[1]` in the evidence list looked like something you'd press. Changed to
`1.` format, updated footer to "Type a number to examine evidence", and wired bare numbers
in `handle_message` to `_do_examine` so typing `1` works exactly like `/examine 1`.

**Password gate:** Added `TELEGRAM_BOT_PASSWORD` support. Unauthenticated users hit a lock
prompt on any message or command. Correct password marks them authenticated once in the DB
(`detective_players.authenticated`). Migration 009 adds the column.

## 2026-06-21 00:00 — Deployed to Railway (Stage 8)

Created new Railway project `true-crime-detective`. Production runs the FastAPI webhook app
(`src/agent/agents/detective/app.py`) — same code as polling, different entrypoint. Updated
`railway.toml` accordingly. Set all environment variables via CLI: ENVIRONMENT=production,
DATABASE_URL (same Neon instance, prefixed tables keep separation), OPENROUTER_API_KEY,
TELEGRAM_BOT_PASSWORD, generated TELEGRAM_WEBHOOK_SECRET and CRON_SECRET, PUBLIC_URL.

The app registers the webhook with Telegram on startup via `lifespan`. Migrations run on
startup too. Both cases (Müller, Bartlett) are confirmed in the production database.

Pending: prod TELEGRAM_BOT_TOKEN needs to be set via `railway variables --set` (kept out
of chat for security). Once set, Railway redeploys and webhook registers automatically.

**What's next:** Ingest Kate Webster and/or Israel Lipski for a third case. Consider
deploying a Railway Cron service for the `/cron/nudge` endpoint (hints for stale sessions).

## 2026-06-22 11:00 — Ingested 5 new cases; added inline keyboard buttons
Ingested all 5 suggested cases via `detective-ingest --url`:
- pearcey-1890 (t18901124-43) — 51 chunks, guilty
- cream-1892 (t18921017-962) — 78 chunks, guilty
- chapman-1903 (t19030309-318) — 86 chunks, guilty
- wood-1907 (t19071210-29) — 107 chunks, not guilty (Camden Town murder, acquitted)
- seddon-1912 (t19120227-48) — 132 chunks, guilty

Finding case numbers for post-1900 Old Bailey sessions required probing URL ranges
(t{date}-{n}) since those sessions don't print case numbers in the running text. Surrey
cases within a session continue the same numbering (Cream = 962, after Middlesex cases
1–961 in t18921017).

Replaced the `/accuse · /hint · /close · /record` footer with a proper Telegram inline
keyboard (2×2 grid). Case briefs now explain how to investigate ("type a number or ask
a question") and show four tappable buttons: Accuse, Hint, Close case, My record.
`_next_case_text` now returns `(text, bool)` so callers know whether to attach the
keyboard. Callback dispatch lives in `handle_callback` with `CallbackQueryHandler`.
