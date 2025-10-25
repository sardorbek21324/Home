"""Admin command handlers for family management."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Set

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import settings

router = Router()

logger = logging.getLogger(__name__)

FAMILY_FILE = Path(__file__).resolve().parents[2] / "family_ids.json"


def load_family_ids() -> Set[int]:
    """Load cached family ids from disk."""

    try:
        with FAMILY_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.info("family_ids.json not found, starting with empty family list")
        return set()
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse family_ids.json: %s", exc)
        return set()

    try:
        return {int(value) for value in data}
    except (TypeError, ValueError) as exc:
        logger.warning("Invalid data in family_ids.json: %s", exc)
        return set()


def save_family_ids(ids: Set[int]) -> None:
    """Persist family ids to disk."""

    FAMILY_FILE.write_text(
        json.dumps(sorted(ids), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


FAMILY_IDS: Set[int] = set()


def initialize_family_cache(*, log: bool = False) -> None:
    """Initialize global family cache from storage."""

    global FAMILY_IDS
    FAMILY_IDS = load_family_ids()
    settings.FAMILY_IDS = sorted(FAMILY_IDS)
    if log:
        logger.info(
            "Loaded %s family members from %s",
            len(FAMILY_IDS),
            FAMILY_FILE.name,
        )


initialize_family_cache()


def get_family_ids() -> list[int]:
    """Expose a sorted list of cached family ids."""

    return sorted(FAMILY_IDS)


@router.message(Command("addfamily"))
async def add_family_member(message: Message) -> None:
    """Add a new family member id during runtime."""

    user = message.from_user
    if user is None:
        return

    if user.id not in settings.ADMIN_IDS:
        await message.answer("🚫 У вас нет прав для добавления участников.")
        return

    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "❗ Используйте формат: `/addfamily <Telegram_ID>`",
            parse_mode="Markdown",
        )
        return

    new_id = int(parts[1])

    if new_id in FAMILY_IDS:
        await message.answer(
            "⚠️ Этот пользователь уже есть в списке семьи.",
        )
        return

    FAMILY_IDS.add(new_id)
    save_family_ids(FAMILY_IDS)
    settings.FAMILY_IDS = sorted(FAMILY_IDS)

    logger.info("Admin %s added family member id %s", user.id, new_id)

    await message.answer(
        f"👨‍👩‍👧‍👦 Участник с ID {new_id} добавлен в семью!",
    )
