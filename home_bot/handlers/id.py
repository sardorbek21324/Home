"""Handlers providing personal identification commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


router = Router()


@router.message(Command("myid", "getid", "id"))
async def cmd_myid(message: Message) -> None:
    """Return the Telegram identifier of the current user."""

    user = message.from_user
    if not user:
        await message.answer("❌ Не удалось определить ваш Telegram ID.")
        return

    uid = user.id
    uname = user.username or "—"
    fname = f"{user.first_name or ''} {user.last_name or ''}".strip()

    text = (
        f"👤 *Ваш Telegram ID:* `{uid}`\n"
        f"🧾 Username: @{uname}\n"
        f"📛 Имя: {fname}\n\n"
        "🔹 Отправьте этот ID администратору, чтобы вас добавили в FAMILY_IDS."
    )
    await message.answer(text, parse_mode="Markdown")
