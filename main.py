"""Application entry point."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application, PicklePersistence

from household_bot.bot.handlers import register_handlers
from household_bot.bot.scheduled.monthly_tasks import schedule_monthly_tasks
from household_bot.bot.scheduled.periodic_tasks import schedule_periodic_tasks
from household_bot.bot.scheduled.weekly_tasks import schedule_weekly_tasks
from household_bot.core.config import settings
from household_bot.core.logger import setup_logging
from household_bot.db.database import engine


async def main() -> None:
    setup_logging()

    persistence = PicklePersistence(filepath="bot_persistence")

    application = (
        Application.builder()
        .token(settings.TELEGRAM_TOKEN)
        .persistence(persistence)
        .build()
    )

    register_handlers(application)

    jobstores = {"default": SQLAlchemyJobStore(engine=engine)}
    scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=str(settings.TIMEZONE))

    await schedule_periodic_tasks(scheduler, application)
    await schedule_weekly_tasks(scheduler, application)
    await schedule_monthly_tasks(scheduler, application)

    scheduler.start()

    logging.info("Бот запускается...")
    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
