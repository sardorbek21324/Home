"""Task related commands and callbacks."""

from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..db.models import TaskInstance, TaskStatus, User
from ..db.repo import add_score_event, ensure_user, list_users, reserve_instance, session_scope, submit_report
from ..domain.constants import CANCEL_GRACE_MINUTES, CANCEL_LATE_PENALTY, CLAIM_DEFER_MINUTES
from ..services.notifications import report_keyboard, verification_keyboard


router = Router()


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


@router.callback_query(F.data.startswith("task:claim:"))
async def claim_task(cb: CallbackQuery) -> None:
    if cb.from_user is None:
        return
    _, _, inst_id_str, mode = cb.data.split(":")
    instance_id = int(inst_id_str)

    with session_scope() as session:
        instance = session.get(TaskInstance, instance_id)
        if not instance or instance.status != TaskStatus.open:
            await cb.answer("Задача уже занята.", show_alert=True)
            return
        user = ensure_user(session, cb.from_user.id, cb.from_user.full_name, cb.from_user.username)
        can_defer = mode == "defer"
        if can_defer and instance.deferrals_used >= 2:
            await cb.answer("Отложить можно не больше двух раз.", show_alert=True)
            return
        reserve_instance(session, instance, user, defer=can_defer, defer_minutes=CLAIM_DEFER_MINUTES)
        template_title = instance.template.title

    await cb.message.edit_text(
        f"{template_title} закреплена за {cb.from_user.full_name}. Выполни и пришли фото.",
        reply_markup=report_keyboard(instance_id),
    )
    await cb.answer("Удачи! Не забудь отправить отчёт.")


@router.callback_query(F.data.startswith("task:cancel:"))
async def cancel_task(cb: CallbackQuery) -> None:
    if cb.from_user is None:
        return
    instance_id = int(cb.data.split(":")[2])

    now = datetime.utcnow()
    with session_scope() as session:
        instance = session.get(TaskInstance, instance_id)
        if not instance or instance.status != TaskStatus.reserved:
            await cb.answer("Нечего отменять.")
            return
        user = ensure_user(session, cb.from_user.id, cb.from_user.full_name, cb.from_user.username)
        if instance.assigned_to is None or instance.assigned_to != user.id:
            await cb.answer("Эта задача не на тебе.", show_alert=True)
            return
        reserved_from = instance.reserved_until or instance.created_at
        elapsed = now - reserved_from
        penalty = 0
        if elapsed > timedelta(minutes=CANCEL_GRACE_MINUTES):
            penalty = -CANCEL_LATE_PENALTY
        if penalty:
            add_score_event(session, user, penalty, "Отмена задачи")
        instance.status = TaskStatus.open
        instance.assigned_to = None
        instance.reserved_until = None

    await cb.message.edit_text("Бронь снята. Задача снова доступна всем.")
    await cb.answer("Отменено")


@router.callback_query(F.data.startswith("task:report:"))
async def request_report(cb: CallbackQuery) -> None:
    if cb.from_user is None:
        return
    instance_id = int(cb.data.split(":")[2])
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
        other_ids = [(other.tg_id, other.name) for other in list_users(session) if other.id != user.id]
        instance_id = instance.id

    await message.answer("Фото получено. Ожидаем голоса семьи!")
    from ..main import scheduler

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

    if scheduler:
        scheduler.schedule_vote_deadline(instance_id)
