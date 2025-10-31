from __future__ import annotations

"""Administrative commands available to bot owners."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

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
    create_task_template,
    ensure_user,
    get_dispute,
    list_open_disputes,
    reset_month,
    resolve_dispute,
    session_scope,
)
from ..utils.telegram import answer_safe
from ..utils.text import escape_html
from ..services.scoring import reward_for_completion
from ..services.scheduler import get_lifecycle_controller

if TYPE_CHECKING:
    from ..services.scheduler import BotScheduler


router = Router()
log = logging.getLogger(__name__)


class AddMicrotask(StatesGroup):
    waiting_input = State()


def _get_scheduler() -> "BotScheduler | None":
    return get_lifecycle_controller()


def _require_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in settings.ADMIN_IDS)


@router.message(Command("announce"))
async def manual_announce(message: Message) -> None:
    if not _require_admin(message):
        await answer_safe(message, "Только администратор может это делать.")
        return

    with session_scope() as session:
        instance = (
            session.query(TaskInstance)
            .filter(TaskInstance.status == TaskStatus.open)
            .order_by(TaskInstance.created_at.asc())
            .first()
        )
        if not instance:
            await answer_safe(message, "Нет открытых задач.")
            return
        instance_id = instance.id

    lifecycle = _get_scheduler()
    if lifecycle is None:
        await answer_safe(message, "Планировщик не активен.")
        return

    await lifecycle.announce_instance(instance_id, penalize=False)
    await answer_safe(message, "Задача объявлена повторно.")
    log.info("Admin %s triggered manual announce for instance %s", message.from_user.id, instance_id)


@router.message(Command("add_task"))
async def add_task(message: Message) -> None:
    if not _require_admin(message):
        await answer_safe(message, "Команда доступна только администраторам.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await answer_safe(
            message,
            "Использование: /add_task code;Название;баллы;frequency;max_per_day;sla;claim_timeout;kind;penalty",
        )
        return
    try:
        fields = [item.strip() for item in parts[1].split(";")]
        if len(fields) < 8:
            raise ValueError
        code, title, base_points, frequency, max_per_day, sla, claim_timeout, kind, *rest = fields
        penalty = rest[0] if rest else "0"
    except ValueError:
        await answer_safe(message, "Не удалось распарсить параметры.")
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
    safe_title = escape_html(title)
    await answer_safe(message, f"Шаблон {safe_title} добавлен.")
    log.info("Admin %s added task template %s", message.from_user.id, code)


@router.message(Command("add_microtask"))
async def add_microtask_start(message: Message, state: FSMContext) -> None:
    if not _require_admin(message):
        await answer_safe(message, "Команда доступна только администраторам.")
        return
    await answer_safe(
        message,
        "Введите микрозадачу в формате: название;баллы;частота (daily/weekly/monthly)",
    )
    await state.set_state(AddMicrotask.waiting_input)


@router.message(AddMicrotask.waiting_input)
async def add_microtask_process(message: Message, state: FSMContext) -> None:
    if not _require_admin(message):
        await answer_safe(message, "Команда доступна только администраторам.")
        await state.clear()
        return
    raw = message.text or ""
    parts = [part.strip() for part in raw.split(";")]
    if len(parts) != 3:
        await answer_safe(message, "Нужно указать три значения через точку с запятой.")
        return
    name, points_raw, freq = parts
    freq = freq.lower()
    if freq not in {"daily", "weekly", "monthly"}:
        await answer_safe(message, "Частота должна быть daily/weekly/monthly")
        return
    try:
        points = int(points_raw)
    except ValueError:
        await answer_safe(message, "Баллы должны быть числом.")
        return
    code = f"micro_{uuid4().hex[:8]}"
    with session_scope() as session:
        create_task_template(
            session,
            code=code,
            name=name,
            points=points,
            frequency=freq,
            max_per_day=1,
            sla=None,
            claim_timeout=60,
            kind=TaskKind.micro,
            penalty=0,
        )
    await answer_safe(message, "Микрозадача добавлена.")
    await state.clear()
    log.info(
        "Admin %s added microtask template %s (freq=%s)",
        message.from_user.id,
        code,
        freq,
    )


@router.message(Command("regen_today"))
async def regen_today(message: Message) -> None:
    if not _require_admin(message):
        await answer_safe(message, "Команда доступна только администраторам.")
        return

    lifecycle = _get_scheduler()
    if lifecycle is None:
        await answer_safe(message, "Планировщик не инициализирован.")
        return

    created = await lifecycle.regenerate_today()
    await answer_safe(message, f"Задачи на сегодня обновлены. Создано: {created}.")
    log.info("Admin %s triggered regen_today (created=%s)", message.from_user.id, created)


@router.message(Command("disputes"))
async def list_disputes(message: Message) -> None:
    if not _require_admin(message):
        await answer_safe(message, "Команда доступна только администраторам.")
        return

    with session_scope() as session:
        disputes = list_open_disputes(session)
        if not disputes:
            await answer_safe(message, "Открытых споров нет.")
            return
        lines = ["⚖️ Открытые споры:"]
        for dispute in disputes:
            instance = dispute.task_instance
            performer = session.get(User, instance.assigned_to) if instance.assigned_to else None
            opener = session.get(User, dispute.opened_by)
            title = escape_html(instance.template.title)
            performer_name = escape_html(performer.name) if performer else "неизвестно"
            opener_name = (
                escape_html(opener.name) if opener else escape_html(str(dispute.opened_by))
            )
            note_text = escape_html(dispute.note or "—")
            lines.append(
                f"#{dispute.id} — {title} (исполнитель: {performer_name})\n"
                f"    Открыл: {opener_name}, примечание: {note_text}"
            )
    await answer_safe(message, "\n".join(lines))


@router.message(Command("resolve_dispute"))
async def resolve_dispute_cmd(message: Message) -> None:
    if not _require_admin(message):
        await answer_safe(message, "Команда доступна только администраторам.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await answer_safe(message, "Использование: /resolve_dispute <id> <approve|reject> <комментарий>")
        return
    _, dispute_id_str, remainder = parts
    try:
        dispute_id = int(dispute_id_str)
    except ValueError:
        await answer_safe(message, "ID спора должен быть числом.")
        return
    action, _, note = remainder.partition(" ")
    approve = action.lower() == "approve"
    if action.lower() not in {"approve", "reject"}:
        await answer_safe(message, "Второй аргумент: approve или reject.")
        return

    with session_scope() as session:
        dispute = get_dispute(session, dispute_id)
        if not dispute or dispute.state != DisputeState.open:
            await answer_safe(message, "Спор не найден или уже закрыт.")
            return
        instance = dispute.task_instance
        performer = session.get(User, instance.assigned_to) if instance.assigned_to else None
        if approve and performer:
            reward = reward_for_completion(instance)
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

    await answer_safe(message, "Спор обновлён.")
    lifecycle = _get_scheduler()
    if lifecycle:
        await lifecycle.announce_pending_tasks()
    log.info(
        "Dispute %s resolved by %s with approve=%s", dispute_id, message.from_user.id, approve
    )


@router.message(Command("end_month"))
async def end_month(message: Message) -> None:
    if not _require_admin(message):
        await answer_safe(message, "Команда доступна только администраторам.")
        return

    season = datetime.now().strftime("%Y-%m")
    with session_scope() as session:
        users = session.query(User).order_by(User.score.desc()).all()
        snapshot = [
            (escape_html(user.name or user.username or str(user.tg_id)), user.score)
            for user in users
        ]
        winner = reset_month(session, season)

    if not snapshot:
        await answer_safe(message, "Нет участников для подведения итогов.")
        return

    lines = [
        f"{idx + 1}. {name} — {score} баллов" for idx, (name, score) in enumerate(snapshot)
    ]
    winner_text = (
        f"🥇 Победитель: {escape_html(winner.name or '')} ({winner.score} баллов)"
        if winner
        else "Нет победителей"
    )
    await answer_safe(
        message,
        f"🏁 Завершён сезон {season}.\n"
        + "\n".join(lines)
        + f"\n\n{winner_text}",
    )
    log.info("Season %s closed by %s", season, message.from_user.id)
