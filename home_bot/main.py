"""Entrypoint for running the Telegram bot."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from datetime import date

from .config import settings
from .db.repo import init_db, seed_templates, session_scope
from .handlers import admin, common, menu, score, tasks, verification
from .handlers.start import router as start_router
from .services.scheduler import BotScheduler, load_seed_templates
from .utils.logging import setup_logging


bot: Bot | None = None
dp: Dispatcher | None = None
scheduler: BotScheduler | None = None


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Запустить"),
        BotCommand(command="menu", description="Меню"),
        BotCommand(command="rating", description="Таблица лидеров"),
        BotCommand(command="history", description="История"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(commands)


async def run_bot() -> None:
    global bot, dp, scheduler

    setup_logging()
    logging.getLogger(__name__).info("Starting bot…")

    init_db()
    with session_scope() as session:
        seed_templates(session, load_seed_templates())

    bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(menu.router)
    dp.include_router(common.router)
    dp.include_router(score.router)
    dp.include_router(tasks.router)
    dp.include_router(verification.router)
    dp.include_router(admin.router)

    scheduler = BotScheduler(bot)
    scheduler.start()
    await scheduler.generate_tasks_for_day(date.today())

    await set_commands(bot)

    while True:
        try:
            await dp.start_polling(bot)
        except Exception as exc:
            logging.getLogger(__name__).warning("Polling error: %s", exc, exc_info=True)
            await asyncio.sleep(5)
        else:
            break


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
