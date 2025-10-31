"""Telegram bot entry point used by hosting platforms."""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.error import Conflict

from .config import BOT_TOKEN

# --- Administrative configuration -------------------------------------------------
ADMIN_USER_ID = 133405512
TARGET_CHAT_ID = 1003166751384


@dataclass
class Task:
    """A scheduled group task."""

    name: str
    times: List[time]
    jobs: List[str] = field(default_factory=list)


@dataclass
class PendingAssignment:
    """Represents a task occurrence awaiting acceptance."""

    task_name: str
    chat_id: int
    message_id: int
    created_at: datetime
    accepted_by: int | None = None


TASKS: Dict[str, Task] = {}
PENDING_ASSIGNMENTS: Dict[str, PendingAssignment] = {}

ASK_TASK_NAME, ASK_TASK_TIMES = range(2)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Привет! Отправь /ping, чтобы проверить, что бот живой."
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to /ping to confirm the bot is alive."""
    await update.message.reply_text("Бот работает! ✅")


async def user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the Telegram identifier of the requesting user."""
    user = update.effective_user
    if user is None:
        logger.warning("Received /id command without an effective user")
        return

    await update.message.reply_text(
        f"Твой Telegram ID: {user.id}"
    )


async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the identifier of the current chat (group, supergroup, or channel)."""
    chat = update.effective_chat
    if chat is None:
        logger.warning("Received /chatid command without an effective chat")
        return

    await update.message.reply_text(
        f"ID этого чата: {chat.id}"
    )


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == ADMIN_USER_ID)


async def admin_only(update: Update) -> bool:
    """Send a warning if a non-admin tries to use an admin command."""

    if _is_admin(update):
        return True

    message = update.effective_message
    if message:
        await message.reply_text("Эта команда доступна только администратору.")
    return False


async def start_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only(update):
        return ConversationHandler.END

    await update.message.reply_text(
        "Введите название задания, которое нужно добавить."
    )
    return ASK_TASK_NAME


async def receive_task_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only(update):
        return ConversationHandler.END

    context.user_data["task_name"] = update.message.text.strip()
    await update.message.reply_text(
        "Укажите времена в формате ЧЧ:ММ через запятую (например, 08:00, 12:00, 18:00)."
    )
    return ASK_TASK_TIMES


def _parse_times(raw: str) -> List[time]:
    parts = [segment.strip() for segment in raw.split(",") if segment.strip()]
    parsed: List[time] = []
    for part in parts:
        try:
            hour, minute = map(int, part.split(":", maxsplit=1))
            parsed.append(time(hour=hour, minute=minute))
        except (ValueError, TypeError):
            raise ValueError(part) from None
    if not parsed:
        raise ValueError("empty")
    return parsed


async def receive_task_times(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only(update):
        return ConversationHandler.END

    raw_times = update.message.text.strip()
    try:
        times = _parse_times(raw_times)
    except ValueError as err:
        await update.message.reply_text(
            "Не удалось распознать время. Убедитесь, что формат ЧЧ:ММ и значения разделены запятыми."
        )
        logger.error("Failed to parse time segment '%s'", err)
        return ASK_TASK_TIMES

    task_name = context.user_data.pop("task_name", "Задание")

    await _register_task(context, task_name, times)

    formatted_times = ", ".join(t.strftime("%H:%M") for t in times)
    await update.message.reply_text(
        f"Задание '{task_name}' добавлено. Время напоминаний: {formatted_times}."
    )
    return ConversationHandler.END


async def cancel_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await admin_only(update):
        return ConversationHandler.END

    await update.message.reply_text("Добавление задания отменено.")
    context.user_data.clear()
    return ConversationHandler.END


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_only(update):
        return

    if not TASKS:
        await update.message.reply_text("Список заданий пуст.")
        return

    lines = []
    for task in TASKS.values():
        times = ", ".join(t.strftime("%H:%M") for t in task.times)
        lines.append(f"• {task.name}: {times}")
    await update.message.reply_text("Текущие задания:\n" + "\n".join(lines))


async def _register_task(
    context: ContextTypes.DEFAULT_TYPE, task_name: str, times: List[time]
) -> None:
    application = context.application

    # Cancel previous jobs for the task if it already existed
    existing = TASKS.get(task_name)
    if existing:
        for job_name in existing.jobs:
            job = application.job_queue.get_jobs_by_name(job_name)
            for entry in job:
                entry.schedule_removal()

    job_names: List[str] = []
    for reminder_time in times:
        job_name = f"task:{task_name}:{reminder_time.strftime('%H%M')}"
        job_names.append(job_name)
        application.job_queue.run_daily(
            send_task_notification,
            time=reminder_time,
            data={"task_name": task_name},
            name=job_name,
        )

    TASKS[task_name] = Task(name=task_name, times=times, jobs=job_names)


async def send_task_notification(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if not job:
        return

    task_name = job.data.get("task_name") if job.data else "Задание"
    event_id = f"{task_name}:{int(datetime.now().timestamp())}"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="Принять",
                    callback_data=f"accept|{event_id}",
                )
            ]
        ]
    )

    message = await context.bot.send_message(
        chat_id=TARGET_CHAT_ID,
        text=f"Задание: {task_name}\nКто готов выполнить?",
        reply_markup=keyboard,
    )

    PENDING_ASSIGNMENTS[event_id] = PendingAssignment(
        task_name=task_name,
        chat_id=message.chat_id,
        message_id=message.message_id,
        created_at=datetime.now(),
    )


async def accept_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    if not query.data.startswith("accept|"):
        await query.answer()
        return

    event_id = query.data.split("|", maxsplit=1)[1]
    assignment = PENDING_ASSIGNMENTS.get(event_id)
    if assignment is None:
        await query.answer("Задание больше недоступно.", show_alert=True)
        return

    if assignment.accepted_by:
        await query.answer("Задание уже принято другим участником.", show_alert=True)
        return

    user = query.from_user
    assignment.accepted_by = user.id if user else -1

    performer = user.mention_html() if user else "Кто-то"
    await context.bot.edit_message_text(
        chat_id=assignment.chat_id,
        message_id=assignment.message_id,
        text=(
            f"Задание: {assignment.task_name}\n"
            f"Исполнитель: {performer}"
        ),
        parse_mode=ParseMode.HTML,
    )

    del PENDING_ASSIGNMENTS[event_id]

    await query.answer("Задание за тобой!", show_alert=False)


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_only(update):
        return

    await update.message.reply_text(
        "Администраторские команды:\n"
        "/addtask — добавить новое задание (будет задан диалог).\n"
        "/listtasks — показать все задания.\n"
        "/cancel — отменить добавление задания."
    )


async def handle_application_error(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Gracefully handle errors raised by the bot."""

    error = context.error
    if isinstance(error, Conflict):
        logger.error(
            "Another polling instance is already running. "
            "Stopping the current application."
        )
        application = context.application
        if application:
            try:
                if application.running:
                    await application.stop()
                await application.shutdown()
            except RuntimeError as exc:
                logger.warning(
                    "Skipping shutdown because the application is still stopping: %s",
                    exc,
                )
        return

    logger.error(
        "Unhandled error while processing update %s",
        update,
        exc_info=(type(error), error, error.__traceback__) if error else None,
    )


def main() -> None:
    """Run the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("addtask", start_add_task)],
        states={
            ASK_TASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_name)],
            ASK_TASK_TIMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_times)],
        },
        fallbacks=[CommandHandler("cancel", cancel_add_task)],
        name="add_task_conversation",
        persistent=False,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("id", user_id))
    application.add_handler(CommandHandler("chatid", chat_id))
    application.add_handler(CommandHandler("admin", admin_help))
    application.add_handler(CommandHandler("listtasks", list_tasks))
    application.add_handler(conversation_handler)
    application.add_handler(CallbackQueryHandler(accept_task))
    application.add_error_handler(handle_application_error)

    logger.info("Bot is starting. Waiting for commands…")
    try:
        application.run_polling()
    except Conflict:
        logger.error(
            "Another polling instance is already running. Exiting the current process."
        )
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
