"""Entrypoint for running the Telegram bot."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand

from .config import settings
from .db.repo import init_db, seed_templates, session_scope
from .handlers import (
    admin,
    ai_admin,
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
        BotCommand(command="ai_test", description="Проверка AI-контроллера"),
        BotCommand(command="ai_stats", description="Админ: статистика AI"),
        BotCommand(command="ai_config", description="Админ: параметры AI"),
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
    global bot, dp

    setup_logging()
    logging.getLogger(__name__).info("Starting bot...")

    init_db()
    with session_scope() as session:
        seed_templates(session, load_seed_templates())

    session = AiohttpSession(timeout=15)
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
    dp.include_router(ai_test.router)
    dp.include_router(ai_admin.router)
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
    await shared_scheduler.ensure_today_tasks(announce=False)

    try:
        await bot.delete_webhook(
            drop_pending_updates=True,
            request_timeout=10,
        )
    except TelegramNetworkError:
        logging.getLogger(__name__).warning(
            "delete_webhook timeout — продолжаю без ошибки"
        )
    await set_commands(bot)

    scheduler_jobs = shared_scheduler.scheduler.get_jobs()
    next_run = None
    for job in scheduler_jobs:
        if job.next_run_time and (next_run is None or job.next_run_time < next_run):
            next_run = job.next_run_time
    logging.getLogger(__name__).info(
        "Scheduler info: tz=%s, jobs=%s, next_run=%s",
        settings.TZ,
        len(scheduler_jobs),
        next_run.isoformat() if next_run else "—",
    )

    try:
        await dp.start_polling(bot)
    finally:
        shared_scheduler.shutdown()
        set_lifecycle_controller(None)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
