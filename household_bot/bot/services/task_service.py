"""Business logic for handling household tasks."""
from __future__ import annotations

import logging
from datetime import timedelta

from telegram import Bot
from telegram.ext import Application, ContextTypes

from household_bot.core.config import settings
from household_bot.db.database import get_session
from household_bot.db.models import TaskStatus
from household_bot.db.repository import DBRepository
from household_bot.bot.keyboards import get_task_proposal_keyboard

from .rotation import get_next_in_rotation

TASK_POINTS = {
    "Приготовить завтрак": {"success": 20, "failure": -15},
    "Приготовить обед": {"success": 20, "failure": -15},
    "Приготовить ужин": {"success": 20, "failure": -15},
    "Загрузить посудомойку": {"success": 10, "failure": -8},
    "Пропылесосить дом": {"success": 15, "failure": -10},
    "Убраться дома": {"success": 12, "failure": -8},
    "Помыть шторы": {"success": 40, "failure": -25},
    "Купить продукты": {"success": 25, "failure": -15},
    "Помыть санузел": {"success": 20, "failure": -12},
}


async def create_and_propose_task(
    bot: Bot,
    application: Application,
    task_name: str,
    category: str,
) -> None:
    """Create a task and propose it to the group chat."""
    async with get_session() as session:
        repo = DBRepository(session)
        points = TASK_POINTS.get(task_name)
        if not points:
            logging.error("No points configured for task '%s'", task_name)
            return

        new_task = await repo.create_task(name=task_name, category=category)

    await bot.send_message(
        chat_id=settings.GROUP_CHAT_ID,
        text=(
            f"🍳 Пора {task_name.lower()}! Кто возьмёт? +{points['success']} баллов"
        ),
        reply_markup=get_task_proposal_keyboard(new_task.id),
    )

    job_queue = application.job_queue
    job_queue.run_once(
        handle_no_reaction,
        when=timedelta(minutes=5),
        data={"task_id": new_task.id},
        name=f"quick_timer_{new_task.id}",
    )
    job_queue.run_once(
        handle_total_silence,
        when=timedelta(minutes=30),
        data={"task_id": new_task.id},
        name=f"hard_timer_{new_task.id}",
    )


async def handle_no_reaction(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Assign the task by rotation after short silence."""
    job = context.job
    if job is None:
        return
    task_id = job.data["task_id"]

    async with get_session() as session:
        repo = DBRepository(session)
        task = await repo.get_task(task_id)
        if task and task.status == TaskStatus.PENDING:
            assignee_id = await get_next_in_rotation(session, task.category)
            assignee = await repo.get_user(assignee_id)

            await repo.assign_task(task_id, assignee_id)

            await context.bot.send_message(
                chat_id=settings.GROUP_CHAT_ID,
                text=(
                    f"Задача '{task.name}' назначена {assignee.first_name if assignee else assignee_id} "
                    "по ротации."
                ),
            )
            context.job_queue.run_once(
                ask_for_progress,
                when=timedelta(minutes=10),
                data={"task_id": task_id},
                name=f"progress_check_{task_id}",
            )


async def handle_total_silence(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Apply penalties if no-one reacts at all."""
    job = context.job
    if job is None:
        return
    task_id = job.data["task_id"]

    async with get_session() as session:
        repo = DBRepository(session)
        task = await repo.get_task(task_id)
        if task and task.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED):
            await repo.update_task_status(task_id, TaskStatus.MISSED)
            await repo.apply_group_penalty(penalty=-5)

            await context.bot.send_message(
                chat_id=settings.GROUP_CHAT_ID,
                text=(
                    "🚨 Задача '{task}' пропущена из-за отсутствия реакции. "
                    "Групповой штраф -5 баллов каждому."
                ).format(task=task.name),
            )


async def ask_for_progress(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reminder asking the assigned user to share progress."""
    job = context.job
    if job is None:
        return
    task_id = job.data["task_id"]

    async with get_session() as session:
        repo = DBRepository(session)
        task = await repo.get_task(task_id)
        if task and task.status == TaskStatus.ASSIGNED:
            assignee = await repo.get_user(task.assignee_id)
            mention = assignee.first_name if assignee else "Исполнитель"
            await context.bot.send_message(
                chat_id=settings.GROUP_CHAT_ID,
                text=f"{mention}, как продвигается задача '{task.name}'?",
            )
