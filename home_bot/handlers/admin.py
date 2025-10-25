"""Admin-only commands."""

from __future__ import annotations

from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import settings
from ..db.models import TaskFrequency, TaskInstance, TaskKind, TaskStatus, TaskTemplate, User
from ..db.repo import reset_month, session_scope


router = Router()


def _require_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in settings.ADMIN_IDS)


@router.message(Command("announce"))
async def manual_announce(message: Message) -> None:
    if not _require_admin(message):
        await message.answer("Только администратор может это делать.")
        return

    with session_scope() as session:
        instance = (
            session.query(TaskInstance)
            .filter(TaskInstance.status == TaskStatus.open)
            .order_by(TaskInstance.created_at.asc())
            .first()
        )
        if not instance:
            await message.answer("Нет открытых задач.")
            return
        instance_id = instance.id

    from ..main import scheduler

    if scheduler is None:
        await message.answer("Планировщик не активен.")
        return

    await scheduler.announce_instance(instance_id, penalize=False)
    await message.answer("Задача объявлена повторно.")


@router.message(Command("add_task"))
async def add_task(message: Message) -> None:
    if not _require_admin(message):
        await message.answer("Команда доступна только администраторам.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование: /add_task code;Название;баллы;frequency;max_per_day;sla;claim_timeout;kind"
        )
        return
    try:
        code, title, base_points, frequency, max_per_day, sla, claim_timeout, kind = [
            item.strip() for item in parts[1].split(";")
        ]
    except ValueError:
        await message.answer("Не удалось распарсить параметры.")
        return

    with session_scope() as session:
        template = TaskTemplate(
            code=code,
            title=title,
            base_points=int(base_points),
            frequency=TaskFrequency(frequency),
            max_per_day=int(max_per_day) if max_per_day else None,
            sla_minutes=int(sla),
            claim_timeout_minutes=int(claim_timeout),
            kind=TaskKind(kind),
        )
        session.add(template)
    await message.answer(f"Шаблон {title} добавлен.")


@router.message(Command("end_month"))
async def end_month(message: Message) -> None:
    if not _require_admin(message):
        await message.answer("Команда доступна только администраторам.")
        return

    season = datetime.now().strftime("%Y-%m")
    with session_scope() as session:
        users = session.query(User).order_by(User.score.desc()).all()
        snapshot = [(user.name, user.score) for user in users]
        reset_month(session, season)

    if not snapshot:
        await message.answer("Нет участников для подведения итогов.")
        return

    lines = [f"{idx + 1}. {name} — {score} баллов" for idx, (name, score) in enumerate(snapshot)]
    winner_name, winner_score = snapshot[0]
    await message.answer(
        "🏁 Завершён сезон {season}.\n".format(season=season)
        + "\n".join(lines)
        + f"\n\n🥇 Победитель: {winner_name} ({winner_score} баллов)"
    )
