"""Scheduler setup for weekly tasks."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from household_bot.core.config import settings


async def schedule_weekly_tasks(scheduler: AsyncIOScheduler, application: Application) -> None:
    bot = application.bot
    scheduler.add_job(
        bot.send_message,
        trigger="cron",
        day_of_week="sat",
        hour=11,
        minute=0,
        timezone=settings.TIMEZONE,
        id="weekly_cleaning",
        replace_existing=True,
        kwargs={
            "chat_id": settings.GROUP_CHAT_ID,
            "text": "🧹 Время для еженедельной уборки!",
        },
    )
