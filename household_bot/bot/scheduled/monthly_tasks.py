"""Scheduler setup for monthly routines."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from household_bot.core.config import settings


async def schedule_monthly_tasks(scheduler: AsyncIOScheduler, application: Application) -> None:
    bot = application.bot
    scheduler.add_job(
        bot.send_message,
        trigger="cron",
        day=1,
        hour=10,
        minute=0,
        timezone=settings.TIMEZONE,
        id="monthly_summary",
        replace_existing=True,
        kwargs={
            "chat_id": settings.GROUP_CHAT_ID,
            "text": "📊 Месячный отчёт скоро будет готов!",
        },
    )
