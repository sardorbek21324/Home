"""Entrypoint for running the Telegram bot."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import ClientTimeout
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.types import BotCommand

from datetime import date

from .config import settings
from .db.repo import init_db, seed_templates, session_scope
from .handlers import admin, common, diagnostics, id as id_handler, menu, score, tasks, verification
from .handlers.start import router as start_router
from .services.scheduler import (
    BotScheduler,
    load_seed_templates,
    set_lifecycle_controller,
)
from .utils.logging import setup_logging


bot: Bot | None = None
dp: Dispatcher | None = None
scheduler: BotScheduler | None = None


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="menu", description="Открыть меню"),
        BotCommand(command="rating", description="Таблица лидеров"),
        BotCommand(command="me", description="Мой баланс"),
        BotCommand(command="history", description="История"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="myid", description="Показать мой Telegram ID"),
    ]
    try:
        await bot.set_my_commands(commands)
    except Exception as exc:  # pragma: no cover - network
        logging.getLogger(__name__).warning(
            "Skip set_my_commands due to network issue: %s", exc
        )


async def run_bot() -> None:
    global bot, dp, scheduler

    setup_logging()
    logging.getLogger(__name__).info("Starting bot...")

    init_db()
    with session_scope() as session:
        seed_templates(session, load_seed_templates())

    session = AiohttpSession(timeout=ClientTimeout(total=20))
    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.workflow_data.update({"settings": settings})
    dp.include_router(start_router)
    dp.include_router(id_handler.router)
    dp.include_router(menu.router)
    dp.include_router(common.router)
    dp.include_router(score.router)
    dp.include_router(tasks.router)
    dp.include_router(verification.router)
    dp.include_router(admin.router)
    dp.include_router(diagnostics.router)

    scheduler = BotScheduler(bot)
    set_lifecycle_controller(scheduler)
    scheduler.start()
    await scheduler.generate_tasks_for_day(date.today())

    await set_commands(bot)
    try:
        while True:
            try:
                await dp.start_polling(bot)
            except TelegramRetryAfter as exc:
                delay = exc.retry_after + 1
                logging.getLogger(__name__).warning("Telegram rate limit. Sleep %s s", delay)
                await asyncio.sleep(delay)
            except TelegramNetworkError as exc:
                logging.getLogger(__name__).warning("Network issue: %s", exc, exc_info=True)
                await asyncio.sleep(5)
            else:
                break
    finally:
        scheduler.shutdown()
        set_lifecycle_controller(None)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
