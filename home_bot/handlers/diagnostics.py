"""Runtime diagnostics helpers."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import settings
from ..services.ai_advisor import quick_ai_ping
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
        f"- {job.id}: next={job.next_run_time}"
        for job in jobs
    ) or "—"

    ai_status = await quick_ai_ping()

    try:
        await message.answer("🔎 Self-test: echo ok", disable_notification=True)
        tg_status = "ok"
    except Exception as exc:  # pragma: no cover - network
        tg_status = f"ошибка: {exc.__class__.__name__}"

    text = (
        "✅ SELFTEST\n"
        f"Admins: {admins}\n"
        f"Family: {family}\n"
        f"Scheduler running: {running}\n"
        f"Jobs:\n{jobs_info}\n"
        f"Telegram: {tg_status}\n"
        f"{ai_status}\n"
        "Если что-то '—' или 'ошибка' — проверь настройки."
    )
    await message.answer(text)
