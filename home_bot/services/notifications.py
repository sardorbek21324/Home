"""Helpers for constructing and sending inline keyboards and messages."""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..db.repo import BroadcastRecord, add_task_broadcasts, session_scope

log = logging.getLogger(__name__)


def _task_keyboard(instance_id: int, *, allow_first: bool, allow_second: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏁 Беру", callback_data=f"claim:{instance_id}")
    if allow_first:
        builder.button(
            text="⏳ Через 30 мин (−20%)",
            callback_data=f"postpone:{instance_id}:1",
        )
    if allow_second:
        builder.button(
            text="⏳ Через 60 мин (−40%)",
            callback_data=f"postpone:{instance_id}:2",
        )
    builder.button(text="🚫 Отменить бронь", callback_data=f"cancel:{instance_id}")
    builder.adjust(1)
    return builder.as_markup()


def report_keyboard(instance_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📸 Отправить отчёт", callback_data=f"report:{instance_id}")
    builder.button(text="↩️ Отменить", callback_data=f"cancel:{instance_id}")
    builder.adjust(1)
    return builder.as_markup()


def verification_keyboard(instance_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да", callback_data=f"vote:{instance_id}:yes")
    builder.button(text="❌ Нет", callback_data=f"vote:{instance_id}:no")
    builder.adjust(2)
    return builder.as_markup()


async def announce_task(
    bot: Bot,
    *,
    task_id: int,
    template_title: str,
    text: str,
    recipients: Sequence[tuple[int, int]],
    allow_first_postpone: bool,
    allow_second_postpone: bool,
) -> None:
    """Send task announce to all recipients and remember message ids."""

    keyboard = _task_keyboard(
        task_id,
        allow_first=allow_first_postpone,
        allow_second=allow_second_postpone,
    )
    delivered: list[BroadcastRecord] = []
    for user_id, chat_id in recipients:
        try:
            message = await bot.send_message(chat_id, text, reply_markup=keyboard)
        except Exception as exc:  # pragma: no cover - network
            log.warning("Failed to announce task %s to %s: %s", task_id, chat_id, exc)
            continue
        delivered.append(
            BroadcastRecord(
                task_id=task_id,
                user_id=user_id,
                chat_id=chat_id,
                message_id=message.message_id,
            )
        )
    if delivered:
        with session_scope() as session:
            add_task_broadcasts(session, delivered)
    log.info(
        "Announcement stored for task %s (recipients=%s)",
        task_id,
        len(delivered),
    )


async def update_after_claim(
    bot: Bot,
    *,
    broadcasts: Iterable[BroadcastRecord],
    claimer_user_id: int,
    claimer_name: str,
    template_title: str,
) -> None:
    """Edit previously sent keyboards once the task has been claimed."""

    records = list(broadcasts)
    update_text = f"🏁 {template_title}\nЗадачу взял {claimer_name}."
    updated = 0
    for record in records:
        if record.user_id == claimer_user_id:
            continue
        try:
            await bot.edit_message_text(
                update_text,
                chat_id=record.chat_id,
                message_id=record.message_id,
            )
            updated += 1
        except Exception as exc:  # pragma: no cover - network
            log.warning(
                "Failed to update announcement for task %s (chat=%s): %s",
                record.task_id,
                record.chat_id,
                exc,
            )
    if updated:
        task_id = next((record.task_id for record in records if record.user_id != claimer_user_id), None)
    else:
        task_id = None
    log.info(
        "Announcement keyboards updated for task_id=%s (updated=%s, title=%s)",
        task_id,
        updated,
        template_title,
    )


async def send_verification_requests(
    bot: Bot,
    *,
    task_id: int,
    template_title: str,
    performer_name: str,
    photo_file_id: str,
    recipients: Sequence[tuple[int, int]],
) -> None:
    """Deliver verification photo to all reviewers and persist message ids."""

    caption = (
        f"Задача: {template_title}\n"
        f"Исполнитель: {performer_name}. Подтверждаешь?"
    )
    keyboard = verification_keyboard(task_id)
    delivered: list[BroadcastRecord] = []
    for user_id, chat_id in recipients:
        try:
            message = await bot.send_photo(
                chat_id,
                photo=photo_file_id,
                caption=caption,
                reply_markup=keyboard,
            )
        except Exception as exc:  # pragma: no cover - network
            log.warning(
                "Failed to send verification for task %s to %s: %s",
                task_id,
                chat_id,
                exc,
            )
            continue
        delivered.append(
            BroadcastRecord(
                task_id=task_id,
                user_id=user_id,
                chat_id=chat_id,
                message_id=message.message_id,
            )
        )
    if delivered:
        with session_scope() as session:
            add_task_broadcasts(session, delivered)
    log.info(
        "Verification messages stored for task %s (recipients=%s)",
        task_id,
        len(delivered),
    )


async def update_verification_messages(
    bot: Bot,
    *,
    broadcasts: Sequence[BroadcastRecord],
    template_title: str,
    performer_name: str,
    verdict_text: str,
) -> None:
    """Update verification messages with the final verdict."""

    caption = (
        f"Задача: {template_title}\n"
        f"Исполнитель: {performer_name}.\n"
        f"Результат: {verdict_text}"
    )
    updated = 0
    for record in broadcasts:
        try:
            await bot.edit_message_caption(
                caption,
                chat_id=record.chat_id,
                message_id=record.message_id,
                reply_markup=None,
            )
            updated += 1
        except Exception as exc:  # pragma: no cover - network
            log.warning(
                "Failed to update verification message for task %s (chat=%s): %s",
                record.task_id,
                record.chat_id,
                exc,
            )
    log.info(
        "Verification messages updated for task %s (updated=%s)",
        template_title,
        updated,
    )
