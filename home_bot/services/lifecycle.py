"""Register recurring background jobs for the bot lifecycle."""

from __future__ import annotations

from aiogram import Bot
from apscheduler.triggers.cron import CronTrigger

from .scheduler import get_scheduler


def schedule_daily_jobs(bot: Bot) -> None:
    """Ensure core periodic jobs are scheduled on the shared scheduler."""

    scheduler = get_scheduler()
    try:
        lifecycle = bot["lifecycle"]
    except KeyError as exc:  # pragma: no cover - configuration guard
        raise RuntimeError("Lifecycle controller is not attached to the bot") from exc

    scheduler.add_job(
        lifecycle.generate_today_tasks,
        CronTrigger(hour=4, minute=0),
        id="tasks:daily",
        replace_existing=True,
        misfire_grace_time=0,
    )
    scheduler.add_job(
        lifecycle.check_missed_tasks,
        "interval",
        minutes=10,
        id="tasks:missed",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lifecycle.check_vote_deadlines,
        "interval",
        minutes=5,
        id="tasks:votes",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
