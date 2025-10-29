"""Runtime diagnostics helpers."""

from __future__ import annotations

import textwrap
from time import perf_counter

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import settings
from ..db.repo import session_scope
from ..services.ai_controller import AIController
from ..services.scheduler import get_scheduler
from sqlalchemy import select
from ..utils.telegram import answer_safe


def _is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in settings.ADMIN_IDS)

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
    timezone = settings.TZ
    job_count = len(jobs)

    try:
        await message.bot.get_me()
        tg_status = "ok"
    except Exception as exc:  # pragma: no cover - network
        tg_status = f"ошибка — {exc.__class__.__name__}"

    controller = AIController()
    db_latency_ms = 0.0
    ai_latency_ms = 0.0
    with session_scope() as session:
        start_db = perf_counter()
        session.execute(select(1))
        db_latency_ms = (perf_counter() - start_db) * 1000
        start_ai = perf_counter()
        stats = controller.get_user_stats(session)
        config = controller.get_config(session)
        ai_status = controller.healthcheck(session)
        ai_latency_ms = (perf_counter() - start_ai) * 1000
    if stats:
        stats_lines = "\n".join(
            f"    {item.name}: coef={item.coefficient:.2f} (взято={item.taken}, пропущено={item.skipped})"
            for item in stats
        )
    else:
        stats_lines = "    —"

    text = textwrap.dedent(
        f"""
        ✅ SELFTEST
        Admins: {admins}
        Family: {family}
        Scheduler running: {running}
        Scheduler timezone: {timezone}
        Scheduled jobs ({job_count}):
        {jobs_info}
        Telegram API: {tg_status}
        DB latency: {db_latency_ms:.1f} ms
        AI: {ai_status} (latency {ai_latency_ms:.1f} ms)
        AI config: penalty={config.penalty_step:.2f}, bonus={config.bonus_step:.2f}, range={config.min_coefficient:.2f}-{config.max_coefficient:.2f}
        AI stats:
{stats_lines}
        Если что-то '—' или 'ошибка' — проверь настройки.
        """
    ).strip()

    await answer_safe(message, text)


@router.message(Command("debug_jobs"))
async def debug_jobs(message: Message) -> None:
    if not _is_admin(message.from_user and message.from_user.id):
        await answer_safe(message, "Команда доступна только администраторам.")
        return
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()
    if not jobs:
        await answer_safe(message, "Планировщик активен, но задач нет.")
        return
    lines = ["🛠 Активные задания планировщика:"]
    for job in jobs:
        next_run = job.next_run_time.isoformat() if job.next_run_time else "—"
        lines.append(f"• <code>{job.id}</code> → {next_run}")
    await answer_safe(message, "\n".join(lines))
