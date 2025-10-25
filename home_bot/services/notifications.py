"""Helpers for constructing inline keyboards and messages."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def task_announce_keyboard(instance_id: int, *, can_defer: bool, can_cancel: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Беру", callback_data=f"task:claim:{instance_id}:now")
    if can_defer:
        builder.button(text="⏳ Беру через 30 мин (−20%)", callback_data=f"task:claim:{instance_id}:defer")
    if can_cancel:
        builder.button(text="↩️ Отмена", callback_data=f"task:cancel:{instance_id}")
    builder.adjust(1)
    return builder.as_markup()


def report_keyboard(instance_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📸 Отправить отчёт", callback_data=f"task:report:{instance_id}")
    builder.button(text="↩️ Отменить", callback_data=f"task:cancel:{instance_id}")
    builder.adjust(1)
    return builder.as_markup()


def verification_keyboard(instance_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да", callback_data=f"vote:{instance_id}:yes")
    builder.button(text="❌ Нет", callback_data=f"vote:{instance_id}:no")
    builder.adjust(2)
    return builder.as_markup()
