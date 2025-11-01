"""Callback handlers for interactive task messages."""
from __future__ import annotations

from datetime import timedelta

from telegram import Update
from telegram.ext import ContextTypes

from household_bot.db.database import get_session
from household_bot.db.models import TaskStatus
from household_bot.db.repository import DBRepository
from household_bot.bot.services.task_service import ask_for_progress, reannounce_task


async def handle_task_accept(
    update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int
) -> None:
    """Handle the "accept" button press for a task."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    user_id = query.from_user.id

    async with get_session() as session:
        repo = DBRepository(session)
        task = await repo.get_task(task_id)
        if not task or task.status != TaskStatus.PENDING:
            await query.answer("Эта задача уже недоступна.", show_alert=True)
            return

        await repo.assign_task(task_id, user_id)

    for job_name in (
        f"quick_timer_{task_id}",
        f"hard_timer_{task_id}",
        f"postpone_timer_{task_id}",
    ):
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

    context.job_queue.run_once(
        ask_for_progress,
        when=timedelta(minutes=10),
        data={"task_id": task_id},
        name=f"progress_check_{task_id}",
    )

    await query.edit_message_text(
        f"✅ Задача закреплена за {query.from_user.first_name}."
    )
    await query.answer()


async def handle_task_decline(
    update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int
) -> None:
    """Handle the "decline" button press for a task."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    user_id = query.from_user.id

    async with get_session() as session:
        repo = DBRepository(session)
        await repo.update_user_score(user_id, -5)

    await query.answer("Понимаем. Штраф -5 баллов.", show_alert=True)


async def handle_task_postpone(
    update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int
) -> None:
    """Handle the "postpone" button press for a task."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return

    async with get_session() as session:
        repo = DBRepository(session)
        task = await repo.get_task(task_id)
        if not task or task.status != TaskStatus.PENDING:
            await query.answer("Задачу уже обрабатывают.", show_alert=True)
            return
        task_name = task.name

    for job_name in (
        f"quick_timer_{task_id}",
        f"hard_timer_{task_id}",
    ):
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

    for job in context.job_queue.get_jobs_by_name(f"postpone_timer_{task_id}"):
        job.schedule_removal()

    context.job_queue.run_once(
        reannounce_task,
        when=timedelta(minutes=30),
        data={"task_id": task_id},
        name=f"postpone_timer_{task_id}",
    )

    await query.edit_message_text(
        f"⏳ Задача '{task_name}' отложена на 30 минут по просьбе {query.from_user.first_name}."
    )
    await query.answer("Отложили задачу на 30 минут.")
