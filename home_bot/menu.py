"""Reply keyboard helpers for the main bot menu."""

from __future__ import annotations

from aiogram import types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from .config import settings


def build_menu_keyboard(user: types.User | None = None) -> ReplyKeyboardMarkup:
    """Return the persistent reply keyboard for quick navigation."""

    user_id = getattr(user, "id", None)
    is_admin = bool(user_id and user_id in settings.ADMIN_IDS)
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text="📊 Баланс"), KeyboardButton(text="📝 Задачи")],
        [KeyboardButton(text="📅 История")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Админ")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

