"""Scheduler setup for periodic tasks."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from household_bot.core.config import settings
from household_bot.bot.services.task_service import create_and_propose_task


async def schedule_periodic_tasks(
    scheduler: AsyncIOScheduler, application: Application
) -> None:
    bot = application.bot
    meal_times = {
        "Приготовить завтрак": "7:00",
        "Приготовить обед": "13:00",
        "Приготовить ужин": "19:00",
    }
    for name, time_value in meal_times.items():
        hour, minute = map(int, time_value.split(":", maxsplit=1))
        scheduler.add_job(
            create_and_propose_task,
            trigger="cron",
            hour=hour,
            minute=minute,
            timezone=settings.TIMEZONE,
            args=[bot, application, name, "food"],
            id=f"meal_{name.replace(' ', '_')}",
            replace_existing=True,
        )

    scheduler.add_job(
        create_and_propose_task,
        trigger="interval",
        days=45,
        start_date="2025-01-01 12:00:00",
        timezone=settings.TIMEZONE,
        args=[bot, application, "Помыть шторы", "periodic"],
        id="wash_curtains",
        replace_existing=True,
    )
