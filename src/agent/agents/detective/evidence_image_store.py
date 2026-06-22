"""Generate and cache Victorian-era evidence illustrations via fal.ai.

On first examine: generate a temp fal.ai image URL (no R2 needed).
After the bot sends the photo, Telegram returns a permanent file_id —
that file_id is stored in detective_evidence_images and reused by every
subsequent examine, instantly and for free.
"""

from __future__ import annotations

from loguru import logger

from agent.agents.detective.models import EvidenceItem
from agent.services import db, media

_IMAGE_MODEL = "fal-ai/flux/schnell"

_PROMPT = (
    "Victorian newspaper engraving, black and white woodcut illustration, "
    "detailed crosshatching and fine line art, 1880s London criminal case. "
    "Evidence item: {label}. {summary}. "
    "Forensic, period-accurate, dramatic. No text, labels, or captions in the image."
)


async def get_image_ref(case_id: int, evidence_id: str) -> str | None:
    """Return the cached Telegram file_id for this evidence item, or None."""
    row = await db.fetchrow(
        "SELECT image_url FROM detective_evidence_images WHERE case_id = $1 AND evidence_id = $2",
        case_id,
        evidence_id,
    )
    return str(row["image_url"]) if row else None


async def store_image_ref(case_id: int, evidence_id: str, file_id: str) -> None:
    """Cache a Telegram file_id for this evidence item."""
    await db.execute(
        """
        INSERT INTO detective_evidence_images (case_id, evidence_id, image_url)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING
        """,
        case_id,
        evidence_id,
        file_id,
    )


async def generate_image(item: EvidenceItem) -> str | None:
    """Generate a Victorian illustration and return the fal.ai temp URL.

    The caller is responsible for sending it to Telegram and caching the
    returned file_id via store_image_ref(). Returns None on any failure.
    """
    prompt = _PROMPT.format(label=item.label, summary=item.summary)
    try:
        result = await media.text_to_image(prompt, model=_IMAGE_MODEL)
    except Exception as exc:
        logger.warning("Image generation failed for {}: {}", item.id, exc)
        return None

    if not result.files:
        logger.warning("Image generation returned no files for {}", item.id)
        return None

    logger.info("Generated evidence image for {} ({})", item.id, item.label)
    return result.files[0].url
