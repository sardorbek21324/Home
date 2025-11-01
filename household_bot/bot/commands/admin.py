"""Administrator commands."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from household_bot.core.config import settings
from household_bot.bot.services.task_service import TASK_POINTS, create_and_propose_task


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or user.id != settings.ADMIN_ID:
        await update.effective_message.reply_text(
            "Эта команда доступна только администратору."
        )
        return

    await update.effective_message.reply_text(
        "Панель администратора: используйте /force_task <название>, чтобы запустить задачу."
    )


async def force_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or user.id != settings.ADMIN_ID:
        await update.effective_message.reply_text(
            "Эта команда доступна только администратору."
        )
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Укажите название задачи: /force_task <название>"
        )
        return

    task_name = " ".join(context.args)
    if task_name not in TASK_POINTS:
        await update.effective_message.reply_text(
            "Для этой задачи не настроены баллы. Добавьте её в TASK_POINTS."
        )
        return
    if context.application is None:
        await update.effective_message.reply_text(
            "Приложение ещё не инициализировано. Попробуйте позже."
        )
        return
    await create_and_propose_task(context.bot, context.application, task_name, "manual")
    await update.effective_message.reply_text(
        f"Задача '{task_name}' запущена."
    )
