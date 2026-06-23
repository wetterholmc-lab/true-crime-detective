"""Telegram bot for The True-Crime Detective.

Run locally with long polling:
    uv run detective

In production the same handlers run via webhook — see app.py.

State machine (all state lives in the DB, not context.user_data):
  - On any message: look up active session.
  - If session.pending_accusation: treat the message as the accusation text.
  - Otherwise: treat the message as a free-form investigation question.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agent.agents.detective import (
    accusation_extractor,
    case_store,
    chunk_store,
    evidence_image_store,
    game_master,
    player_store,
    scorer,
    session_store,
)
from agent.agents.detective.models import Score, SessionStatus, Verdict
from agent.config import get_settings
from agent.logging_setup import setup_logging
from agent.services import db
from agent.services.llm import embed_one

MIGRATIONS_DIR = Path(__file__).parents[4] / "migrations"

COMMANDS = [
    BotCommand("examine", "Examine evidence: /examine 1  or  /examine hat"),
    BotCommand("accuse", "Make your formal accusation"),
    BotCommand("hint", "Request a nudge from the record"),
    BotCommand("close", "Close the case without accusing (reveals verdict)"),
    BotCommand("record", "Your detective record"),
    BotCommand("newcase", "Move on to the next case"),
]

_WELCOME = (
    "🔎 Welcome, Detective.\n\n"
    "You investigate real historical cases — Old Bailey, Victorian London. "
    "The evidence is genuine. The verdict is real.\n\n"
    "Examine evidence, question the record, make your accusation. "
    "Then find out what history decided.\n\n"
    "Let me find your first case..."
)

_HOW_TO_INVESTIGATE = (
    "🔍 Investigate: type a number to examine evidence, or ask any question about the case.\n"
    "⚖️ If you need more hints or are ready to accuse: use the buttons below."
)

_SCORE_LINES: dict[Score, str] = {
    Score.CORRECT: "✅ Correct — right person, right verdict.",
    Score.WRONG_VERDICT: "⚠️ Right suspect, wrong verdict.",
    Score.WRONG_PERSON: "❌ Wrong suspect.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_token() -> str:
    token = get_settings().telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Add your @BotFather token to .env.")
    return token


def _action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚖️ Accuse", callback_data="accuse"),
            InlineKeyboardButton("🕵️ Hint", callback_data="hint"),
        ],
        [
            InlineKeyboardButton("📁 Close case", callback_data="close"),
            InlineKeyboardButton("🗂 My record", callback_data="record"),
        ],
    ])


def _case_brief_text(case: case_store.CaseRecord) -> str:  # type: ignore[name-defined]
    return (
        f"🔎 A new case has crossed your desk, Detective.\n\n"
        f"{case.title}\n"
        f"{case.court}, {case.year}\n\n"
        f"{case.brief}\n\n"
        f"Evidence on file:\n{_evidence_lines(case)}\n\n"
        f"{_HOW_TO_INVESTIGATE}"
    )


async def _next_case_text(telegram_id: int) -> tuple[str, bool]:
    """Return (text, has_case). has_case=True means the action keyboard should be shown."""
    case = await case_store.get_next_case(telegram_id)
    if case is None:
        record = await player_store.get_player_record(telegram_id)
        pct = _pct(record.cases_correct, record.cases_attempted)
        return (
            "🗂 You've cleared the case file, Detective.\n\n"
            f"Cases investigated: {record.cases_attempted}\n"
            f"Correct verdicts: {record.cases_correct}/{record.cases_attempted} ({pct}%)\n\n"
            "No new cases are loaded yet. Check back soon.",
            False,
        )
    await session_store.open_session(telegram_id, case.id)
    return _case_brief_text(case), True


def _pct(correct: int, attempted: int) -> int:
    return round(correct / attempted * 100) if attempted else 0


def _evidence_lines(case: case_store.CaseRecord) -> str:  # type: ignore[name-defined]
    return "\n".join(f"  {i + 1}. {e.label}" for i, e in enumerate(case.evidence))


async def _authed(telegram_id: int) -> bool:
    """True if no password is configured, or the user has already entered it."""
    pw = get_settings().telegram_bot_password
    if not pw:
        return True
    return await player_store.is_authenticated(telegram_id)


async def _build_reveal(
    telegram_id: int,
    case: case_store.CaseRecord,  # type: ignore[name-defined]
    score: Score | None,
    accusation_name: str | None,
    accusation_verdict: Verdict | None,
) -> str:
    """Record the outcome and return the verdict reveal text."""
    await player_store.record_outcome(telegram_id, score)
    record = await player_store.get_player_record(telegram_id)
    pct = _pct(record.cases_correct, record.cases_attempted)

    if score is not None and accusation_name and accusation_verdict:
        v_label = "Guilty" if accusation_verdict == Verdict.GUILTY else "Not Guilty"
        header = f"{_SCORE_LINES[score]}\nYou said: {accusation_name} — {v_label}\n\n"
    else:
        header = ""

    return (
        f"{header}"
        f"THE REAL VERDICT:\n{case.verdict_text}\n\n"
        f"{case.aftermath_text}\n\n"
        f"🏅 DETECTIVE RECORD: "
        f"{record.cases_correct}/{record.cases_attempted} correct · {pct}% accuracy\n\n"
        f"When you're ready for the next case: /newcase"
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not await _authed(user.id):
        await update.message.reply_text(
            "🔒 This bot is password-protected.\n\nEnter the password to begin:"
        )
        return
    await player_store.get_or_create_player(user.id)
    active = await session_store.get_active_session(user.id)
    if active:
        case = await case_store.get_case(active.case_id)
        await update.message.reply_text(
            f"Welcome back, Detective. You're mid-case:\n\n"
            f"{case.title}\n\n"
            f"Evidence on file:\n{_evidence_lines(case)}\n\n"
            f"{_HOW_TO_INVESTIGATE}",
            reply_markup=_action_keyboard(),
        )
    else:
        await update.message.reply_text(_WELCOME)
        text, has_case = await _next_case_text(user.id)
        await update.message.reply_text(
            text, reply_markup=_action_keyboard() if has_case else None
        )


async def _send_evidence_photo(
    update: Update,
    case_id: int,
    label: str,
    item: case_store.EvidenceItem,  # type: ignore[name-defined]
    image_ref: str,
) -> None:
    """Send an evidence photo, upgrading any cached temp URL to a Telegram file_id.

    If the ref is a fal.ai temp URL that has expired, regenerates the image and
    retries once. Silently skips the photo if both attempts fail (text follows).
    """
    if update.message is None:
        return
    try:
        msg = await update.message.reply_photo(image_ref, caption=f"📁 {label}")
    except Exception:
        # Temp URL likely expired — regenerate and retry once.
        logger.info("Cached image ref failed for {}; regenerating", item.id)
        fresh = await evidence_image_store.generate_image(item)
        if not fresh:
            return
        try:
            msg = await update.message.reply_photo(fresh, caption=f"📁 {label}")
        except Exception:
            return  # give up; text description follows
    # Always upgrade the stored ref to the permanent Telegram file_id.
    if msg.photo:
        await evidence_image_store.store_image_ref(case_id, item.id, msg.photo[-1].file_id)


async def _do_examine(
    update: Update,
    session: session_store.Session,  # type: ignore[name-defined]
    ref: str | int,
) -> None:
    """Core examine logic — shared by /examine command and bare-number shortcut."""
    if update.message is None:
        return
    item = await case_store.get_evidence_item(session.case_id, ref)
    if item is None:
        await update.message.reply_text(
            "That item isn't in the evidence list. Type a number from 1 to examine evidence.",
            reply_markup=_action_keyboard(),
        )
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    case = await case_store.get_case(session.case_id)
    query_emb = await embed_one(f"{item.label} {item.summary}")
    chunks = await chunk_store.search_chunks(session.case_id, query_emb, k=3)

    question = f"Describe this evidence item from the record: {item.label}"
    cached_ref = await evidence_image_store.get_image_ref(session.case_id, item.id)

    if cached_ref:
        # Cache hit: use stored Telegram file_id + run description only.
        description = await game_master.answer_question(case, chunks, question)
        image_ref: str | None = cached_ref
    else:
        # Cache miss: generate illustration and description in parallel.
        description, image_ref = await asyncio.gather(
            game_master.answer_question(case, chunks, question),
            evidence_image_store.generate_image(item),
        )

    await session_store.mark_evidence_examined(session.id, item.id)
    await session_store.touch_session(session.id)

    if image_ref:
        await _send_evidence_photo(update, session.case_id, item.label, item, image_ref)
        await update.message.reply_text(description, reply_markup=_action_keyboard())
    else:
        await update.message.reply_text(
            f"📁 EVIDENCE: {item.label}\n\n{description}", reply_markup=_action_keyboard()
        )


async def handle_examine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not await _authed(user.id):
        await update.message.reply_text("🔒 Enter the password first.")
        return
    session = await session_store.get_active_session(user.id)
    if session is None:
        await update.message.reply_text("No active case. Send /start to begin.")
        return
    arg = " ".join(context.args or []).strip()
    if not arg:
        await update.message.reply_text(
            "Which item? Type a number, e.g. /examine 1", reply_markup=_action_keyboard()
        )
        return
    ref: str | int = int(arg) if arg.isdigit() else arg
    await _do_examine(update, session, ref)


async def handle_accuse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not await _authed(user.id):
        await update.message.reply_text("🔒 Enter the password first.")
        return
    session = await session_store.get_active_session(user.id)
    if session is None:
        await update.message.reply_text("No active case. Send /start to begin.")
        return
    await session_store.set_pending_accusation(session.id, True)
    await update.message.reply_text(
        "⚖️ State your accusation, Detective.\n\n"
        "Who do you believe is responsible, and is your verdict Guilty or Not Guilty?\n\n"
        'Example: "I accuse Franz Müller. Guilty."'
    )


async def handle_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not await _authed(user.id):
        await update.message.reply_text("🔒 Enter the password first.")
        return
    session = await session_store.get_active_session(user.id)
    if session is None:
        await update.message.reply_text("No active case. Send /start to begin.")
        return
    if session.hint_count >= 3:
        await update.message.reply_text(
            "You've used all 3 hints for this case, Detective.\n"
            "Make your accusation with /accuse, or close the case with /close.",
            reply_markup=_action_keyboard(),
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    case = await case_store.get_case(session.case_id)
    # Focus on unexamined evidence; fall back to first item
    unexamined = [e for e in case.evidence if e.id not in session.clues_examined]
    focus = unexamined[0] if unexamined else case.evidence[0]
    query_emb = await embed_one(f"{focus.label} {focus.summary}")
    chunks = await chunk_store.search_chunks(session.case_id, query_emb, k=3)
    hint = await game_master.generate_hint(case, chunks, session.clues_examined)

    await session_store.increment_hint_count(session.id)
    new_count = session.hint_count + 1
    closing = "\n\nThat was your last hint. Tap Accuse when ready." if new_count >= 3 else ""
    await update.message.reply_text(
        f"🕵️ A nudge, Detective:\n\n{hint}{closing}", reply_markup=_action_keyboard()
    )


async def handle_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not await _authed(user.id):
        await update.message.reply_text("🔒 Enter the password first.")
        return
    session = await session_store.get_active_session(user.id)
    if session is None:
        await update.message.reply_text("No active case.")
        return
    case = await case_store.get_case(session.case_id)
    await session_store.close_session(session.id, SessionStatus.ABANDONED)
    reveal = await _build_reveal(user.id, case, None, None, None)
    await update.message.reply_text(reveal)


async def handle_record(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not await _authed(user.id):
        await update.message.reply_text("🔒 Enter the password first.")
        return
    record = await player_store.get_player_record(user.id)
    pct = _pct(record.cases_correct, record.cases_attempted)
    await update.message.reply_text(
        f"🗂 YOUR DETECTIVE RECORD\n\n"
        f"Cases investigated: {record.cases_attempted}\n"
        f"Correct ✅: {record.cases_correct}\n"
        f"Wrong verdict ⚠️: {record.cases_wrong_verdict}\n"
        f"Wrong suspect ❌: {record.cases_wrong_person}\n"
        f"Abandoned: {record.cases_abandoned}\n"
        f"Accuracy: {pct}%"
    )


async def handle_newcase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return
    if not await _authed(user.id):
        await update.message.reply_text("🔒 Enter the password first.")
        return
    session = await session_store.get_active_session(user.id)
    if session:
        await session_store.close_session(session.id, SessionStatus.ABANDONED)
        await player_store.record_outcome(user.id, None)
    text, has_case = await _next_case_text(user.id)
    await update.message.reply_text(text, reply_markup=_action_keyboard() if has_case else None)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle taps on the inline action buttons (accuse / hint / close / record)."""
    query = update.callback_query
    user = update.effective_user
    chat = update.effective_chat
    if query is None or user is None or chat is None:
        return
    await query.answer()  # dismiss the button's loading indicator

    action = query.data

    if not await _authed(user.id):
        await context.bot.send_message(chat.id, "🔒 Enter the password first.")
        return

    if action == "record":
        record = await player_store.get_player_record(user.id)
        pct = _pct(record.cases_correct, record.cases_attempted)
        session_for_record = await session_store.get_active_session(user.id)
        await context.bot.send_message(
            chat.id,
            f"🗂 YOUR DETECTIVE RECORD\n\n"
            f"Cases investigated: {record.cases_attempted}\n"
            f"Correct ✅: {record.cases_correct}\n"
            f"Wrong verdict ⚠️: {record.cases_wrong_verdict}\n"
            f"Wrong suspect ❌: {record.cases_wrong_person}\n"
            f"Abandoned: {record.cases_abandoned}\n"
            f"Accuracy: {pct}%",
            reply_markup=_action_keyboard() if session_for_record else None,
        )
        return

    session = await session_store.get_active_session(user.id)
    if session is None:
        await context.bot.send_message(chat.id, "No active case. Send /start to begin.")
        return

    if action == "accuse":
        await session_store.set_pending_accusation(session.id, True)
        await context.bot.send_message(
            chat.id,
            "⚖️ State your accusation, Detective.\n\n"
            "Who do you believe is responsible, and is your verdict Guilty or Not Guilty?\n\n"
            'Example: "I accuse Franz Müller. Guilty."',
        )

    elif action == "hint":
        if session.hint_count >= 3:
            await context.bot.send_message(
                chat.id,
                "You've used all 3 hints for this case, Detective.\n"
                "Tap Accuse, or close the case to see the verdict.",
                reply_markup=_action_keyboard(),
            )
            return
        await context.bot.send_chat_action(chat.id, ChatAction.TYPING)
        case = await case_store.get_case(session.case_id)
        unexamined = [e for e in case.evidence if e.id not in session.clues_examined]
        focus = unexamined[0] if unexamined else case.evidence[0]
        query_emb = await embed_one(f"{focus.label} {focus.summary}")
        chunks = await chunk_store.search_chunks(session.case_id, query_emb, k=3)
        hint = await game_master.generate_hint(case, chunks, session.clues_examined)
        await session_store.increment_hint_count(session.id)
        new_count = session.hint_count + 1
        closing = "\n\nThat was your last hint. Tap Accuse when ready." if new_count >= 3 else ""
        await context.bot.send_message(
            chat.id,
            f"🕵️ A nudge, Detective:\n\n{hint}{closing}",
            reply_markup=_action_keyboard(),
        )

    elif action == "close":
        case = await case_store.get_case(session.case_id)
        await session_store.close_session(session.id, SessionStatus.ABANDONED)
        reveal = await _build_reveal(user.id, case, None, None, None)
        await context.bot.send_message(chat.id, reveal)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None or not update.message.text:
        return

    text = update.message.text.strip()

    # Password gate: treat any message from an unauthenticated user as a password attempt.
    if not await _authed(user.id):
        expected = get_settings().telegram_bot_password
        if expected and text == expected:
            await player_store.set_authenticated(user.id)
            await player_store.get_or_create_player(user.id)
            await update.message.reply_text("✅ Access granted, Detective.")
            next_text, has_case = await _next_case_text(user.id)
            await update.message.reply_text(
                next_text, reply_markup=_action_keyboard() if has_case else None
            )
        else:
            await update.message.reply_text("Wrong password. Try again:")
        return

    session = await session_store.get_active_session(user.id)

    if session is None:
        await player_store.get_or_create_player(user.id)
        await update.message.reply_text(_WELCOME)
        next_text, has_case = await _next_case_text(user.id)
        await update.message.reply_text(
            next_text, reply_markup=_action_keyboard() if has_case else None
        )
        return

    if session.pending_accusation:
        await _process_accusation(update, session, text)
        return

    # Bare number → examine that evidence item (e.g. player types "1" instead of /examine 1)
    if text.isdigit():
        await _do_examine(update, session, int(text))
        return

    # Free-form investigation question
    await update.message.chat.send_action(ChatAction.TYPING)
    case = await case_store.get_case(session.case_id)
    query_emb = await embed_one(text)
    chunks = await chunk_store.search_chunks(session.case_id, query_emb, k=5)
    answer = await game_master.answer_question(case, chunks, text)
    await session_store.touch_session(session.id)
    await update.message.reply_text(answer, reply_markup=_action_keyboard())


async def _process_accusation(
    update: Update,
    session: session_store.Session,  # type: ignore[name-defined]
    text: str,
) -> None:
    if update.message is None or update.effective_user is None:
        return
    user = update.effective_user

    await session_store.set_pending_accusation(session.id, False)
    await update.message.chat.send_action(ChatAction.TYPING)

    extract = await accusation_extractor.extract_accusation(text)
    if extract is None:
        await update.message.reply_text(
            "I didn't catch that, Detective. "
            'Try: "I accuse [Name]. Guilty." — or tap Accuse to try again.',
            reply_markup=_action_keyboard(),
        )
        return

    case = await case_store.get_case(session.case_id)
    score = scorer.score_accusation(extract, case)
    await session_store.close_session(
        session.id,
        SessionStatus.SOLVED,
        accusation_name=extract.name,
        accusation_verdict=extract.verdict,
        score=score,
    )
    reveal = await _build_reveal(user.id, case, score, extract.name, extract.verdict)
    await update.message.reply_text(reveal)


# ---------------------------------------------------------------------------
# Application wiring
# ---------------------------------------------------------------------------


async def post_init(app: Application) -> None:  # type: ignore[type-arg]
    applied = await db.apply_migrations(MIGRATIONS_DIR)
    if applied:
        logger.info("Applied migrations: {}", applied)
    await app.bot.set_my_commands(COMMANDS)


def build_application() -> Application:  # type: ignore[type-arg]
    token = _require_token()
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("examine", handle_examine))
    app.add_handler(CommandHandler("accuse", handle_accuse))
    app.add_handler(CommandHandler("hint", handle_hint))
    app.add_handler(CommandHandler("close", handle_close))
    app.add_handler(CommandHandler("record", handle_record))
    app.add_handler(CommandHandler("newcase", handle_newcase))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


def main() -> None:
    setup_logging()
    logger.info("Starting The True-Crime Detective (polling)...")
    app = build_application()
    app.run_polling(drop_pending_updates=True)
