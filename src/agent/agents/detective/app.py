"""Production entrypoint: FastAPI app hosting the Telegram webhook and the cron nudge.

    uv run fastapi run src/agent/agents/detective/app.py    # production
    uv run fastapi dev  src/agent/agents/detective/app.py   # local webhook mode (optional)

Locally you will normally use polling instead:  uv run detective
This file is what Railway runs. Two endpoints, both protected by secrets:
  POST /telegram/webhook  — Telegram delivers updates here
  POST /cron/nudge        — Railway Cron calls this hourly; sends hints to stale sessions
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from loguru import logger
from telegram import Update
from telegram.ext import Application

from agent.agents.detective import case_store, chunk_store, game_master, session_store
from agent.agents.detective.bot import build_application, post_init
from agent.config import get_settings
from agent.logging_setup import setup_logging
from agent.services.llm import embed_one

_ptb: Application | None = None  # type: ignore[type-arg]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _ptb
    setup_logging()
    settings = get_settings()
    ptb = build_application()
    _ptb = ptb
    await ptb.initialize()
    await post_init(ptb)
    await ptb.start()
    if settings.public_url:
        url = f"{settings.public_url.rstrip('/')}/telegram/webhook"
        await ptb.bot.set_webhook(
            url=url,
            secret_token=settings.telegram_webhook_secret,
            allowed_updates=Update.ALL_TYPES,
        )
        logger.info("Webhook registered at {}", url)
    else:
        logger.warning("PUBLIC_URL not set — webhook not registered")
    yield
    await ptb.stop()
    await ptb.shutdown()


app = FastAPI(title="The True-Crime Detective", lifespan=lifespan)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    settings = get_settings()
    secret = settings.telegram_webhook_secret
    if not secret or not secrets.compare_digest(x_telegram_bot_api_secret_token or "", secret):
        raise HTTPException(status_code=403)
    ptb = _ptb
    if ptb is None:
        raise HTTPException(status_code=503)
    update = Update.de_json(await request.json(), ptb.bot)
    if update is not None:
        await ptb.process_update(update)
    return {"ok": True}


@app.post("/cron/nudge")
async def cron_nudge(x_cron_secret: str | None = Header(default=None)) -> dict[str, int]:
    """Send inactivity hints to players who haven't moved in 24+ hours."""
    settings = get_settings()
    if not settings.cron_secret or not secrets.compare_digest(
        x_cron_secret or "", settings.cron_secret
    ):
        raise HTTPException(status_code=401)
    ptb = _ptb
    if ptb is None:
        raise HTTPException(status_code=503)

    sent = 0
    stale = await session_store.get_stale_sessions(threshold_hours=24)
    for session in stale:
        if session.hint_count >= 3:
            continue
        try:
            case = await case_store.get_case(session.case_id)
            unexamined = [e for e in case.evidence if e.id not in session.clues_examined]
            focus = unexamined[0] if unexamined else case.evidence[0]
            query_emb = await embed_one(f"{focus.label} {focus.summary}")
            chunks = await chunk_store.search_chunks(session.case_id, query_emb, k=3)
            hint = await game_master.generate_hint(case, chunks, session.clues_examined)
            closing = (
                "\n\nThat was your last nudge. /accuse when ready, or /close to see the verdict."
                if session.hint_count + 1 >= 3
                else ""
            )
            await ptb.bot.send_message(
                chat_id=session.telegram_id,
                text=f"🕵️ Still on the {case.title} case, Detective?\n\n{hint}{closing}",
            )
            await session_store.increment_hint_count(session.id)
            sent += 1
        except Exception as exc:
            logger.warning("Failed to nudge session {}: {}", session.id, exc)

    logger.info("Cron nudge: sent {} hints", sent)
    return {"sent": sent}
