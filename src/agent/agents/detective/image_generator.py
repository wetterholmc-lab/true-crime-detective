"""Preview or force-generate evidence illustrations.

Usage:
    uv run detective-generate-images              # list cache status for all cases
    uv run detective-generate-images --slug muller-1864  # one case

Images are cached as Telegram file_ids after the first real player examine,
so pre-generation via this script is optional. Use it to check coverage or
to trigger generation for review purposes (prints the temp fal.ai URLs).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from agent.agents.detective import evidence_image_store
from agent.agents.detective.models import EvidenceItem
from agent.logging_setup import setup_logging
from agent.services import db

MIGRATIONS_DIR = Path(__file__).parents[4] / "migrations"


async def report_case(case_id: int, slug: str, generate: bool) -> None:
    rows = await db.fetch("SELECT evidence_json FROM detective_cases WHERE id = $1", case_id)
    if not rows:
        logger.warning("Case {} not found", slug)
        return

    raw = rows[0]["evidence_json"]
    items: list[dict[str, Any]] = json.loads(raw) if isinstance(raw, str) else raw

    for item_data in items:
        item = EvidenceItem(**item_data)
        cached = await evidence_image_store.get_image_ref(case_id, item.id)
        if cached:
            print(f"  ✓ [{slug}] {item.id}: {item.label}")
        elif generate:
            print(f"  … [{slug}] {item.id}: generating '{item.label}'")
            url = await evidence_image_store.generate_image(item)
            if url:
                print(f"    temp URL: {url}")
            else:
                print("    ✗ generation failed")
        else:
            print(f"  — [{slug}] {item.id}: {item.label}  (not yet cached)")


async def run(slug: str | None, generate: bool) -> None:
    await db.apply_migrations(MIGRATIONS_DIR)

    if slug:
        row = await db.fetchrow("SELECT id, slug FROM detective_cases WHERE slug = $1", slug)
        if not row:
            raise SystemExit(f"No case with slug '{slug}'")
        cases = [row]
    else:
        cases = await db.fetch("SELECT id, slug FROM detective_cases ORDER BY id")

    for row in cases:
        await report_case(row["id"], row["slug"], generate)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Check or generate evidence illustrations")
    parser.add_argument("--slug", help="Only process this case slug")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate missing images (prints temp fal.ai URLs; not cached until first examine)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.slug, args.generate))
