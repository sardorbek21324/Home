"""Runtime diagnostics helpers."""

from __future__ import annotations

import textwrap

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import settings
from ..services.ai_advisor import AIAdvisor
from ..services.scheduler import get_scheduler

router = Router()


@router.message(Command("selftest"))
async def selftest(message: Message) -> None:
    """Run lightweight health checks and report the status."""

    admins = ", ".join(map(str, settings.ADMIN_IDS)) or "—"
    family = ", ".join(map(str, settings.FAMILY_IDS)) or "—"

    scheduler = get_scheduler()
    running = scheduler.running
    jobs = scheduler.get_jobs() if running else []
    jobs_info = "\n".join(
        f"- {job.id}: next={job.next_run_time.isoformat() if job.next_run_time else '—'}"
        for job in jobs
    ) or "—"

    try:
        await message.bot.get_me()
        tg_status = "ok"
    except Exception as exc:  # pragma: no cover - network
        tg_status = f"ошибка — {exc.__class__.__name__}"

    advisor = AIAdvisor()
    ai_status = await advisor.healthcheck()

    text = textwrap.dedent(
        f"""
        ✅ SELFTEST
        Admins: {admins}
        Family: {family}
        Scheduler running: {running}
        Jobs:
        {jobs_info}
        Telegram: {tg_status}
        AI: {ai_status}
        Если что-то '—' или 'ошибка' — проверь настройки.
        """
    ).strip()

    await message.answer(text)


@router.message(Command("debug_jobs"))
async def debug_jobs(message: Message) -> None:
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()
    if not jobs:
        await message.answer("Планировщик активен, но задач нет.")
        return
    lines = ["🛠 Активные задания планировщика:"]
    for job in jobs:
        next_run = job.next_run_time.isoformat() if job.next_run_time else "—"
        lines.append(f"• <code>{job.id}</code> → {next_run}")
    await message.answer("\n".join(lines))
