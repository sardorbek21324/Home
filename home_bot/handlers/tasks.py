from __future__ import annotations

"""Handlers for task lifecycle: claiming, reporting, cancelling."""

import logging
from datetime import datetime, timedelta
from typing import Sequence, TYPE_CHECKING

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..db.models import TaskInstance, TaskStatus, User
from ..db.repo import (
    add_score_event,
    ensure_user,
    list_users,
    reserve_instance,
    session_scope,
    submit_report,
)
from ..domain.constants import CANCEL_GRACE_MINUTES, CANCEL_LATE_PENALTY, CLAIM_DEFER_MINUTES
from ..services.notifications import report_keyboard, verification_keyboard

if TYPE_CHECKING:
    from ..services.scheduler import BotScheduler


router = Router()
log = logging.getLogger(__name__)


def _get_scheduler(bot: Bot) -> "BotScheduler | None":
    return getattr(bot, "lifecycle", None)


def task_keyboard(instance_id: int, can_defer_1: bool, can_defer_2: bool) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🏁 Беру", callback_data=f"claim:{instance_id}")]
    ]
    if can_defer_1:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="⏳ Через 30 мин (−20%)",
                    callback_data=f"defer1:{instance_id}",
                )
            ]
        )
    if can_defer_2:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="⏳ Через 60 мин (−40%)",
                    callback_data=f"defer2:{instance_id}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="🚫 Отменить бронь", callback_data=f"cancel:{instance_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def announce_task(bot: Bot, users: Sequence[int], ti: TaskInstance, text: str) -> None:
    can_defer_1 = True
    can_defer_2 = True
    if getattr(ti, "deferrals_used", 0):
        can_defer_1 = ti.deferrals_used < 1
        can_defer_2 = ti.deferrals_used < 2
    keyboard = task_keyboard(ti.id, can_defer_1, can_defer_2)
    for uid in users:
        try:
            await bot.send_message(uid, text, reply_markup=keyboard)
        except Exception as exc:
            log.warning("Failed to deliver task %s to %s: %s", ti.id, uid, exc)


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


@router.callback_query(F.data.regexp(r"^(claim|defer1|defer2):\\d+$"))
async def claim_task(cb: CallbackQuery) -> None:
    if cb.from_user is None:
        return
    action, _, inst_id_str = cb.data.partition(":")
    if not inst_id_str:
        await cb.answer()
        return
    instance_id = int(inst_id_str)

    with session_scope() as session:
        instance = session.get(TaskInstance, instance_id)
        if not instance or instance.status != TaskStatus.open:
            await cb.answer("Задача уже занята.", show_alert=True)
            return
        user = ensure_user(session, cb.from_user.id, cb.from_user.full_name, cb.from_user.username)
        can_defer = action != "claim"
        if can_defer and instance.deferrals_used >= 2:
            await cb.answer("Отложить можно не больше двух раз.", show_alert=True)
            return
        explicit_deferrals = None
        defer_minutes = 0
        if action == "defer1":
            defer_minutes = CLAIM_DEFER_MINUTES
            explicit_deferrals = min(max(instance.deferrals_used, 0) + 1, 2)
        elif action == "defer2":
            defer_minutes = CLAIM_DEFER_MINUTES * 2
            explicit_deferrals = 2
        deadline = reserve_instance(
            session,
            instance,
            user,
            defer=can_defer,
            defer_minutes=defer_minutes,
            explicit_deferrals=explicit_deferrals,
        )
        template_title = instance.template.title
        deferrals = instance.deferrals_used

    await cb.message.edit_text(
        f"{template_title} закреплена за {cb.from_user.full_name}. Выполни и пришли фото.",
        reply_markup=report_keyboard(instance_id),
    )
    await cb.answer("Удачи! Не забудь отправить отчёт.")
    lifecycle = _get_scheduler(cb.bot)
    if lifecycle:
        lifecycle.cancel_open_jobs(instance_id)
    log.info(
        "Task %s reserved by %s (deferrals=%s, deadline=%s)",
        instance_id,
        cb.from_user.full_name,
        deferrals,
        deadline,
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
        other_candidates = [
            other
            for other in list_users(session)
            if other.id != user.id and other.tg_id is not None
        ]
        other_ids = [(other.tg_id, other.name) for other in other_candidates[:2]]
        instance_id = instance.id

    await message.answer("Фото получено. Ожидаем голоса семьи!")

    for tg_id, _ in other_ids:
        try:
            await message.bot.send_photo(
                tg_id,
                photo=file_id,
                caption=(
                    f"Задача: {template_title}\n"
                    f"Исполнитель: {message.from_user.full_name}. Подтверждаешь?"
                ),
                reply_markup=verification_keyboard(instance.id),
            )
        except Exception:
            continue

    lifecycle = _get_scheduler(message.bot)
    if lifecycle:
        lifecycle.cancel_open_jobs(instance_id)
    log.info(
        "Report submitted for instance %s by %s", instance_id, message.from_user.full_name
    )
