from __future__ import annotations

"""Handlers for task lifecycle: claiming, reporting, cancelling."""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..db.models import TaskInstance, TaskStatus, User
from ..db.repo import (
    add_score_event,
    ensure_user,
    family_users,
    pop_task_broadcasts,
    session_scope,
    submit_report,
    try_claim_task,
)
from ..domain.constants import CANCEL_GRACE_MINUTES, CANCEL_LATE_PENALTY, CLAIM_DEFER_MINUTES
from ..services.notifications import (
    report_keyboard,
    send_verification_requests,
    update_after_claim,
)

if TYPE_CHECKING:
    from ..services.scheduler import BotScheduler


router = Router()
log = logging.getLogger(__name__)


def _get_scheduler(bot: Bot) -> "BotScheduler | None":
    return getattr(bot, "lifecycle", None)


def _format_task(instance: TaskInstance) -> str:
    template = instance.template
    status_map = {
        TaskStatus.open: "открыта",
        TaskStatus.reserved: "в работе",
        TaskStatus.report_submitted: "на проверке",
        TaskStatus.approved: "завершена",
        TaskStatus.rejected: "отклонена",
        TaskStatus.expired: "истекла",
        TaskStatus.missed: "просрочена",
    }
    status = status_map.get(instance.status, instance.status.value)
    return (
        f"{template.title} (+{template.base_points}) — {status}\n"
        f"Слот: {instance.slot}, переносов: {instance.deferrals_used}"
    )


@router.message(Command("tasks"))
async def tasks_list(message: Message) -> None:
    lines = []
    with session_scope() as session:
        instances = (
            session.query(TaskInstance)
            .filter(TaskInstance.status.in_([TaskStatus.open, TaskStatus.reserved]))
            .order_by(TaskInstance.created_at.asc())
            .all()
        )
        for inst in instances:
            lines.append(_format_task(inst))

    if not lines:
        await message.answer("Нет открытых задач. Загляни позже!")
        return

    await message.answer("Доступные задания:\n" + "\n\n".join(lines))


@router.callback_query(F.data.regexp(r"^(claim|postpone):\\d+(?::\\d+)?$"))
async def claim_task(cb: CallbackQuery) -> None:
    if cb.from_user is None or cb.message is None:
        return
    parts = cb.data.split(":")
    if len(parts) < 2:
        await cb.answer()
        return
    action = parts[0]
    instance_id = int(parts[1])
    postpone_level = int(parts[2]) if len(parts) > 2 else 0

    with session_scope() as session:
        instance = session.get(TaskInstance, instance_id)
        if not instance or instance.status != TaskStatus.open:
            await cb.answer("Задача уже занята.", show_alert=True)
            return
        user = ensure_user(session, cb.from_user.id, cb.from_user.full_name, cb.from_user.username)
        template = instance.template
        current_deferrals = max(instance.deferrals_used or 0, 0)
        extra_minutes = 0
        target_deferrals = 0
        if action == "postpone":
            if postpone_level not in (1, 2):
                await cb.answer("Опция недоступна.", show_alert=True)
                return
            if current_deferrals >= 2:
                await cb.answer("Отложить можно не больше двух раз.", show_alert=True)
                return
            if postpone_level == 1:
                target_deferrals = min(current_deferrals + 1, 2)
            else:
                target_deferrals = 2
            if target_deferrals <= current_deferrals:
                await cb.answer("Опция недоступна.", show_alert=True)
                return
            extra_minutes = CLAIM_DEFER_MINUTES * postpone_level
        reserved_until = datetime.utcnow() + timedelta(minutes=template.sla_minutes + extra_minutes)
        success = try_claim_task(
            session,
            instance_id=instance.id,
            user_id=user.id,
            reserved_until=reserved_until,
            deferrals_used=target_deferrals,
        )
        if not success:
            await cb.answer("Задача уже занята.", show_alert=True)
            return
        session.refresh(instance)
        broadcasts = pop_task_broadcasts(session, instance.id)
        template_title = template.title
        deadline = instance.reserved_until
        deferrals = instance.deferrals_used

    await cb.message.edit_text(
        (
            f"{template_title} закреплена за {cb.from_user.full_name}."
            " Выполни и пришли фото."
        ),
        reply_markup=report_keyboard(instance_id),
    )
    await cb.answer("Удачи! Не забудь отправить отчёт.")
    await update_after_claim(
        cb.bot,
        broadcasts=broadcasts,
        claimer_user_id=user.id,
        claimer_name=cb.from_user.full_name,
        template_title=template_title,
    )
    lifecycle = _get_scheduler(cb.bot)
    if lifecycle:
        lifecycle.cancel_open_jobs(instance_id)
    deadline_log = deadline.isoformat() if deadline else "unknown"
    log.info(
        "Task %s reserved by %s (deferrals=%s, deadline=%s)",
        instance_id,
        cb.from_user.full_name,
        deferrals,
        deadline_log,
    )


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_task(cb: CallbackQuery) -> None:
    if cb.from_user is None:
        return
    _, _, inst_id_str = cb.data.partition(":")
    instance_id = int(inst_id_str)

    with session_scope() as session:
        instance = session.get(TaskInstance, instance_id)
        if not instance or instance.status != TaskStatus.reserved:
            await cb.answer("Нечего отменять.")
            return
        user = ensure_user(session, cb.from_user.id, cb.from_user.full_name, cb.from_user.username)
        if instance.assigned_to is None or instance.assigned_to != user.id:
            await cb.answer("Эта задача не на тебе.", show_alert=True)
            return
        now = datetime.utcnow()
        if instance.reserved_until:
            claimed_at = instance.reserved_until - timedelta(
                minutes=instance.template.sla_minutes
                + instance.deferrals_used * CLAIM_DEFER_MINUTES,
            )
        else:
            claimed_at = now
        elapsed = now - claimed_at
        penalty = 0
        if elapsed > timedelta(minutes=CANCEL_GRACE_MINUTES):
            penalty = -CANCEL_LATE_PENALTY
        if penalty:
            add_score_event(session, user, penalty, "Отмена задачи")
        instance.status = TaskStatus.open
        instance.assigned_to = None
        instance.reserved_until = None
        instance.deferrals_used = 0
        session.flush()

    await cb.message.edit_text("Бронь снята. Задача снова доступна всем.")
    await cb.answer("Отменено")
    lifecycle = _get_scheduler(cb.bot)
    if lifecycle:
        lifecycle.cancel_open_jobs(instance_id)
        await lifecycle.announce_instance(instance_id, penalize=False)
    log.info("Reservation for instance %s cancelled by %s", instance_id, cb.from_user.full_name)


@router.callback_query(F.data.startswith("report:"))
async def request_report(cb: CallbackQuery) -> None:
    if cb.from_user is None:
        return
    _, _, inst_id_str = cb.data.partition(":")
    instance_id = int(inst_id_str)
    with session_scope() as session:
        instance = session.get(TaskInstance, instance_id)
        if not instance or instance.status != TaskStatus.reserved:
            await cb.answer("Сначала возьми задачу.", show_alert=True)
            return
        performer = ensure_user(session, cb.from_user.id, cb.from_user.full_name, cb.from_user.username)
        if instance.assigned_to != performer.id:
            await cb.answer("Задача закреплена за другим участником.", show_alert=True)
            return
    await cb.message.answer("Пришли фото-отчёт в ответ на это сообщение.")
    await cb.answer()


@router.message(F.photo)
async def handle_photo(message: Message) -> None:
    if message.from_user is None:
        return
    auto_reject = False
    recipients: list[tuple[int, int]] = []
    instance_id = None
    template_title = ""
    performer_name = message.from_user.full_name
    file_id = message.photo[-1].file_id if message.photo else ""

    with session_scope() as session:
        user = session.query(User).filter(User.tg_id == message.from_user.id).one_or_none()
        if not user:
            await message.answer("Сначала /start")
            return
        instance = (
            session.query(TaskInstance)
            .filter(
                TaskInstance.assigned_to == user.id,
                TaskInstance.status == TaskStatus.reserved,
            )
            .order_by(TaskInstance.created_at.desc())
            .first()
        )
        if not instance:
            await message.answer("Нет задач, ожидающих фото.")
            return
        file_id = message.photo[-1].file_id
        submit_report(session, instance, user, file_id)
        template_title = instance.template.title
        instance_id = instance.id
        family = [member for member in family_users(session) if member.id != user.id and member.tg_id]
        recipients = [(member.id, int(member.tg_id)) for member in family]
        instance.round_no = len(recipients)
        if instance.round_no == 0:
            instance.status = TaskStatus.rejected
            auto_reject = True
        session.flush()

    if auto_reject:
        await message.answer("Фото получено. Проверяющих нет, отчёт отклонён.")
        log.info(
            "Report auto-rejected for instance %s: no reviewers", instance_id
        )
        return

    await message.answer("Фото получено. Ожидаем голоса семьи!")

    await send_verification_requests(
        message.bot,
        task_id=instance_id,
        template_title=template_title,
        performer_name=performer_name,
        photo_file_id=file_id,
        recipients=recipients,
    )

    lifecycle = _get_scheduler(message.bot)
    if lifecycle:
        lifecycle.cancel_open_jobs(instance_id)
        lifecycle.schedule_vote_deadline(instance_id)
    log.info(
        "Report submitted for instance %s by %s (reviewers=%s)",
        instance_id,
        performer_name,
        len(recipients),
    )
