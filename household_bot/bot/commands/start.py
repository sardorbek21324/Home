"""Implementation of the /start command."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from household_bot.db.database import get_session
from household_bot.db.repository import DBRepository


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    async with get_session() as session:
        repo = DBRepository(session)
        await repo.ensure_user(user.id, user.username, user.first_name)

    await update.effective_message.reply_text(
        "Привет! Я помогу распределять бытовые задачи."
    )
