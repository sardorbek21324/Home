"""Implementation of statistics related commands."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from household_bot.db.database import get_session
from household_bot.db.repository import DBRepository


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    async with get_session() as session:
        repo = DBRepository(session)
        record = await repo.get_user(user.id)

    score = record.monthly_score if record else 0
    await update.effective_message.reply_text(
        f"Ваш текущий счёт: {score} баллов."
    )


async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with get_session() as session:
        repo = DBRepository(session)
        users = await repo.list_users_by_score()

    if not users:
        await update.effective_message.reply_text("Рейтинг пока пуст.")
        return

    lines = [
        f"{idx + 1}. {user.first_name or user.username or user.telegram_id}: {user.monthly_score}"
        for idx, user in enumerate(users)
    ]
    await update.effective_message.reply_text("Текущий рейтинг:\n" + "\n".join(lines))
