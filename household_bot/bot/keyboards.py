"""Inline keyboard constructors."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_task_proposal_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Сделаю сейчас", callback_data=f"accept:{task_id}"),
                InlineKeyboardButton("Не смогу", callback_data=f"decline:{task_id}"),
            ]
        ]
    )
