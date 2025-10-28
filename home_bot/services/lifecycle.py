"""Register recurring background jobs for the bot lifecycle."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.triggers.cron import CronTrigger

from ..config import settings
from .scheduler import get_lifecycle_controller, get_scheduler


def schedule_daily_jobs(bot: Bot) -> None:
    """Ensure core periodic jobs are scheduled on the shared scheduler."""

    scheduler = get_scheduler()
    lifecycle = get_lifecycle_controller()
    if lifecycle is None:  # pragma: no cover - configuration guard
        raise RuntimeError("Lifecycle controller is not attached to the bot")

    tz = ZoneInfo(settings.TZ)
    common = dict(
        coalesce=True,
        misfire_grace_time=120,
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        lifecycle.generate_today_tasks,
        CronTrigger(hour=8, minute=0, timezone=tz),
        id="tasks:daily",
        **common,
    )
    scheduler.add_job(
        lifecycle.check_missed_tasks,
        "interval",
        minutes=10,
        id="tasks:missed",
        **common,
    )
    scheduler.add_job(
        lifecycle.check_vote_deadlines,
        "interval",
        minutes=5,
        id="tasks:votes",
        **common,
    )
