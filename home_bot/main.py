"""Entrypoint for running the Telegram bot."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.types import BotCommand

from datetime import date

from .config import settings
from .db.repo import init_db, seed_templates, session_scope
from .handlers import (
    admin,
    ai_test,
    common,
    diagnostics,
    family_admin,
    id as id_handler,
    menu,
    score,
    tasks,
    verification,
)
from .handlers.start import router as start_router
from .services.scheduler import (
    load_seed_templates,
    set_lifecycle_controller,
    shared_scheduler,
)
from .services import family as family_service
from .utils.logging import setup_logging


bot: Bot | None = None
dp: Dispatcher | None = None


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Запустить бота и показать меню"),
        BotCommand(command="menu", description="Открыть меню"),
        BotCommand(command="tasks", description="Задачи сегодня"),
        BotCommand(command="rating", description="Таблица лидеров"),
        BotCommand(command="me", description="Мои баллы"),
        BotCommand(command="history", description="История операций"),
        BotCommand(command="myid", description="Мой Telegram ID"),
        BotCommand(command="selftest", description="Самодиагностика"),
        BotCommand(command="ai_test", description="Проверка OpenAI"),
        BotCommand(command="family_list", description="Админ: список family IDs"),
        BotCommand(command="family_add", description="Админ: добавить family ID"),
        BotCommand(command="family_remove", description="Админ: удалить family ID"),
        BotCommand(command="regen_today", description="Админ: задачи на сегодня"),
        BotCommand(command="debug_jobs", description="Админ: планировщик"),
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

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.workflow_data.update({"settings": settings})
    dp.include_router(start_router)
    dp.include_router(id_handler.router)
    dp.include_router(menu.router)
    dp.include_router(common.router)
    dp.include_router(ai_test.router)
    dp.include_router(score.router)
    dp.include_router(tasks.router)
    dp.include_router(verification.router)
    dp.include_router(family_admin.router)
    dp.include_router(admin.router)
    dp.include_router(diagnostics.router)

    family_service.ensure_loaded(log=True)

    shared_scheduler.attach_bot(bot)
    set_lifecycle_controller(shared_scheduler)
    shared_scheduler.start()
    dp["scheduler"] = shared_scheduler
    await shared_scheduler.generate_tasks_for_day(date.today())

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
        shared_scheduler.shutdown()
        set_lifecycle_controller(None)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
