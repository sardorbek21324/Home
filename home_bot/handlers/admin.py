from __future__ import annotations

"""Administrative commands available to bot owners."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import settings
from ..db.models import (
    DisputeState,
    TaskFrequency,
    TaskInstance,
    TaskKind,
    TaskStatus,
    TaskTemplate,
    User,
)
from ..db.repo import (
    add_score_event,
    ensure_user,
    get_dispute,
    list_open_disputes,
    reset_month,
    resolve_dispute,
    session_scope,
)
from ..services.scoring import reward_for_completion

if TYPE_CHECKING:
    from ..services.scheduler import BotScheduler


router = Router()
log = logging.getLogger(__name__)


def _get_scheduler(bot: Bot) -> "BotScheduler | None":
    return getattr(bot, "lifecycle", None)


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

    lifecycle = _get_scheduler(message.bot)
    if lifecycle is None:
        await message.answer("Планировщик не активен.")
        return

    await lifecycle.announce_instance(instance_id, penalize=False)
    await message.answer("Задача объявлена повторно.")
    log.info("Admin %s triggered manual announce for instance %s", message.from_user.id, instance_id)


@router.message(Command("add_task"))
async def add_task(message: Message) -> None:
    if not _require_admin(message):
        await message.answer("Команда доступна только администраторам.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование: /add_task code;Название;баллы;frequency;max_per_day;sla;claim_timeout;kind;penalty"
        )
        return
    try:
        fields = [item.strip() for item in parts[1].split(";")]
        if len(fields) < 8:
            raise ValueError
        code, title, base_points, frequency, max_per_day, sla, claim_timeout, kind, *rest = fields
        penalty = rest[0] if rest else "0"
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
            nobody_claimed_penalty=int(penalty or 0),
        )
        session.add(template)
    await message.answer(f"Шаблон {title} добавлен.")
    log.info("Admin %s added task template %s", message.from_user.id, code)


@router.message(Command("disputes"))
async def list_disputes(message: Message) -> None:
    if not _require_admin(message):
        await message.answer("Команда доступна только администраторам.")
        return

    with session_scope() as session:
        disputes = list_open_disputes(session)
        if not disputes:
            await message.answer("Открытых споров нет.")
            return
        lines = ["⚖️ Открытые споры:"]
        for dispute in disputes:
            instance = dispute.task_instance
            performer = session.get(User, instance.assigned_to) if instance.assigned_to else None
            opener = session.get(User, dispute.opened_by)
            lines.append(
                f"#{dispute.id} — {instance.template.title} (исполнитель: {performer.name if performer else 'неизвестно'})\n"
                f"    Открыл: {opener.name if opener else dispute.opened_by}, примечание: {dispute.note or '—'}"
            )
    await message.answer("\n".join(lines))


@router.message(Command("resolve_dispute"))
async def resolve_dispute_cmd(message: Message) -> None:
    if not _require_admin(message):
        await message.answer("Команда доступна только администраторам.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /resolve_dispute <id> <approve|reject> <комментарий>")
        return
    _, dispute_id_str, remainder = parts
    try:
        dispute_id = int(dispute_id_str)
    except ValueError:
        await message.answer("ID спора должен быть числом.")
        return
    action, _, note = remainder.partition(" ")
    approve = action.lower() == "approve"
    if action.lower() not in {"approve", "reject"}:
        await message.answer("Второй аргумент: approve или reject.")
        return

    with session_scope() as session:
        dispute = get_dispute(session, dispute_id)
        if not dispute or dispute.state != DisputeState.open:
            await message.answer("Спор не найден или уже закрыт.")
            return
        instance = dispute.task_instance
        performer = session.get(User, instance.assigned_to) if instance.assigned_to else None
        if approve and performer:
            reward = reward_for_completion(instance.template, instance.deferrals_used)
            add_score_event(
                session,
                performer,
                reward,
                f"{instance.template.title}: спор решён",
                task_instance=instance,
            )
        resolver = ensure_user(
            session,
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username,
        )
        resolve_dispute(session, dispute, resolver, note.strip() or "", approve=approve)

    await message.answer("Спор обновлён.")
    log.info(
        "Dispute %s resolved by %s with approve=%s", dispute_id, message.from_user.id, approve
    )


@router.message(Command("end_month"))
async def end_month(message: Message) -> None:
    if not _require_admin(message):
        await message.answer("Команда доступна только администраторам.")
        return

    season = datetime.now().strftime("%Y-%m")
    with session_scope() as session:
        users = session.query(User).order_by(User.score.desc()).all()
        snapshot = [(user.name, user.score) for user in users]
        winner = reset_month(session, season)

    if not snapshot:
        await message.answer("Нет участников для подведения итогов.")
        return

    lines = [f"{idx + 1}. {name} — {score} баллов" for idx, (name, score) in enumerate(snapshot)]
    winner_text = (
        f"🥇 Победитель: {winner.name} ({winner.score} баллов)" if winner else "Нет победителей"
    )
    await message.answer(
        f"🏁 Завершён сезон {season}.\n"
        + "\n".join(lines)
        + f"\n\n{winner_text}"
    )
    log.info("Season %s closed by %s", season, message.from_user.id)
