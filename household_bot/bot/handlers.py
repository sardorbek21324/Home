"""Registration helpers for bot handlers."""
from __future__ import annotations

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from household_bot.bot.callbacks.task_callbacks import (
    handle_task_accept,
    handle_task_decline,
)
from household_bot.bot.commands.admin import admin_panel, force_task
from household_bot.bot.commands.start import start
from household_bot.bot.commands.stats import rating, stats


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("статистика", stats))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("рейтинг", rating))
    application.add_handler(CommandHandler("rating", rating))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("force_task", force_task))

    application.add_handler(
        CallbackQueryHandler(_build_accept_handler(), pattern=r"^accept:\d+")
    )
    application.add_handler(
        CallbackQueryHandler(_build_decline_handler(), pattern=r"^decline:\d+")
    )


def _extract_task_id(update_data: str | None) -> int:
    if not update_data or ":" not in update_data:
        return -1
    _, task_id = update_data.split(":", maxsplit=1)
    return int(task_id)


def _build_accept_handler():
    async def _handler(update, context):
        task_id = _extract_task_id(update.callback_query.data if update.callback_query else None)
        if task_id >= 0:
            await handle_task_accept(update, context, task_id)

    return _handler


def _build_decline_handler():
    async def _handler(update, context):
        task_id = _extract_task_id(update.callback_query.data if update.callback_query else None)
        if task_id >= 0:
            await handle_task_decline(update, context, task_id)

    return _handler
