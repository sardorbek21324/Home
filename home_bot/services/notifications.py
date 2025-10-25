"""Helpers for constructing inline keyboards and messages."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
