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

TASK_MESSAGES = {
    "Приготовить завтрак": "🍳 Пора готовить завтрак! Кто возьмёт? +{points} баллов",
    "Приготовить обед": "🍳 Пора готовить обед! Кто возьмёт? +{points} баллов",
    "Приготовить ужин": "🍳 Пора готовить ужин! Кто возьмёт? +{points} баллов",
    "Загрузить посудомойку": "🧼 Кто уберёт кухню и стол? +{points} баллов",
    "Пропылесосить дом": "🧹 Кто пропылесосит дом? +{points} баллов",
    "Убраться дома": "🧼 Кто наведёт порядок дома? +{points} баллов",
    "Помыть шторы": "🧺 Пора помыть шторы! Кто возьмётся? +{points} баллов",
    "Купить продукты": "🛒 Пора купить продукты! Кто сделает? +{points} баллов",
    "Помыть санузел": "🧽 Нужно помыть санузел. Кто возьмётся? +{points} баллов",
}


def _render_task_message(task_name: str, success_points: int) -> str:
    template = TASK_MESSAGES.get(task_name)
    if template:
        return template.format(points=success_points)
    return f"Новая задача: {task_name}. +{success_points} баллов"


def _schedule_followup_jobs(application: Application, task_id: int) -> None:
    job_queue = application.job_queue
    job_queue.run_once(
        handle_no_reaction,
        when=timedelta(minutes=5),
        data={"task_id": task_id},
        name=f"quick_timer_{task_id}",
    )
    job_queue.run_once(
        handle_total_silence,
        when=timedelta(minutes=30),
        data={"task_id": task_id},
        name=f"hard_timer_{task_id}",
    )


async def _announce_task(
    bot: Bot,
    application: Application,
    task_id: int,
    task_name: str,
) -> None:
    points = TASK_POINTS.get(task_name)
    if not points:
        logging.error("No points configured for task '%s'", task_name)
        return

    await bot.send_message(
        chat_id=settings.GROUP_CHAT_ID,
        text=_render_task_message(task_name, points["success"]),
        reply_markup=get_task_proposal_keyboard(task_id),
    )

    _schedule_followup_jobs(application, task_id)


async def create_and_propose_task(
    bot: Bot,
    application: Application,
    task_name: str,
    category: str,
) -> None:
    """Create a task and propose it to the group chat."""
    async with get_session() as session:
        repo = DBRepository(session)
        new_task = await repo.create_task(name=task_name, category=category)

    await _announce_task(bot, application, new_task.id, task_name)


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


async def reannounce_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-send a postponed task back to the chat."""
    job = context.job
    if job is None:
        return
    task_id = job.data["task_id"]

    async with get_session() as session:
        repo = DBRepository(session)
        task = await repo.get_task(task_id)
        if not task or task.status != TaskStatus.PENDING:
            return
        task_name = task.name

    application = context.application
    if application is None:
        logging.error("Application context missing for task %s reannounce", task_id)
        return

    await _announce_task(context.bot, application, task_id, task_name)
