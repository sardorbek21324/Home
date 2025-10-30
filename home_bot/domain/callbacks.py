"""Callback data definitions used across inline keyboards."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class ClaimTaskCallback(CallbackData, prefix="claim"):
    """Callback for taking a task immediately."""

    task_id: int


class PostponeTaskCallback(CallbackData, prefix="postpone"):
    """Callback for deferring a task claim by a given level."""

    task_id: int
    level: int

