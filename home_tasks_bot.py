"""
Home Tasks Bot
================

This script implements a Telegram bot for coordinating household chores among a
group of friends.  The bot maintains a list of recurring task templates,
generates daily task instances, announces them to a group chat, allows users
to claim and complete tasks, applies penalties for missed deadlines and awards
points for completions.  A leaderboard helps motivate participants through
friendly competition.

Key features
------------

* **Persistent storage** – a simple SQLite database stores users, task
templates, daily task instances and user scores.  Data is preserved between
restarts.
* **Scheduling** – the built‐in job queue from the `python‑telegram-bot`
framework schedules daily generation of tasks and midday announcements.  The
job queue also schedules deadlines for claimed tasks.
* **Commands** – participants interact with the bot via commands:

  - `/start` registers the user and shows basic instructions.
  - `/tasks` lists today’s open and claimed tasks.
  - `/rating` shows the current leaderboard.
  - `/me` shows your own point total.
  - `/addtask` (admin only) creates a new recurring task template.

* **Inline buttons** – tasks are announced with inline buttons that let users
claim and complete tasks.  When a user clicks “Claim”, the task is reserved
for them and a deadline is scheduled.  Clicking “Done” before the deadline
completes the task and awards points.  Missing the deadline reopens the
task and applies a penalty.

Compared with the original project, this implementation favors reliability and
simplicity over experimental AI features.  It does not attempt to predict or
infer behaviour; all state is explicit in the database.  Scheduling uses
`JobQueue.run_daily` from python‑telegram-bot, which creates jobs that run at
specified times each day.  The code avoids long‑running blocking operations and
uses asynchronous handlers throughout.

Before running the bot you must install the `python-telegram-bot` library
(version 20 or newer) and set environment variables:

```
export BOT_TOKEN="your_bot_token"
export FAMILY_CHAT_ID="-1001234567890"  # id of the group where announcements go
export ADMIN_IDS="12345,67890"           # comma separated list of admin user IDs
```

The bot can be started by simply running `python home_tasks_bot.py`.  When
started it will create the database if it does not exist, schedule the daily
jobs and begin polling for updates.

"""

import logging
import os
import sqlite3
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("DB_PATH", "home_tasks.db")


def get_db_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database.

    The connection uses row_factory to yield rows as simple dictionaries.  A
    single connection is created per call; callers should close it when done.
    """

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialise the database if required.

    Creates tables for users, task templates and task instances if they do not
    already exist.  Templates define recurring chores; instances represent
    individual occurrences of a chore on a specific date.
    """

    with get_db_connection() as conn:
        cur = conn.cursor()
        # Users table: id is Telegram ID; score tracks cumulative points.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                tg_id      INTEGER PRIMARY KEY,
                name       TEXT NOT NULL,
                score      INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Task templates define recurring chores.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS task_templates (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                title         TEXT NOT NULL,
                description   TEXT,
                frequency     TEXT NOT NULL,
                base_points   INTEGER NOT NULL,
                penalty       INTEGER NOT NULL
            )
            """
        )
        # Task instances are generated for each day tasks occur.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS task_instances (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id   INTEGER NOT NULL,
                task_date     DATE NOT NULL,
                claimed_by    INTEGER,
                claimed_at    DATETIME,
                due_at        DATETIME,
                status        TEXT NOT NULL,
                announced     INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(template_id) REFERENCES task_templates(id),
                FOREIGN KEY(claimed_by) REFERENCES users(tg_id)
            )
            """
        )
        conn.commit()


def get_or_create_user(tg_id: int, name: str) -> None:
    """Ensure a user exists in the database.

    Updates the stored name if it changed.  Users start with zero points.
    """

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM users WHERE tg_id = ?", (tg_id,))
        row = cur.fetchone()
        if row:
            # Update name if it has changed
            if row["name"] != name:
                cur.execute("UPDATE users SET name = ? WHERE tg_id = ?", (name, tg_id))
        else:
            cur.execute(
                "INSERT INTO users (tg_id, name, score) VALUES (?, ?, 0)",
                (tg_id, name),
            )
        conn.commit()


def list_tasks_for_today(include_completed: bool = False) -> List[sqlite3.Row]:
    """Return a list of today's tasks.

    If include_completed is False, only open or reserved tasks are returned.
    """

    today = date.today().isoformat()
    query = "SELECT ti.id, tt.title, tt.description, ti.status, ti.claimed_by, ti.due_at, tt.base_points, tt.penalty FROM task_instances ti JOIN task_templates tt ON ti.template_id = tt.id WHERE ti.task_date = ?"
    params: Tuple = (today,)
    if not include_completed:
        query += " AND ti.status IN ('open', 'reserved')"
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()


def get_task_instance(task_id: int) -> Optional[sqlite3.Row]:
    """Retrieve a task instance by ID."""

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ti.id, ti.task_date, ti.status, ti.claimed_by, ti.due_at, ti.claimed_at, tt.title, tt.base_points, tt.penalty FROM task_instances ti JOIN task_templates tt ON ti.template_id = tt.id WHERE ti.id = ?",
            (task_id,),
        )
        return cur.fetchone()


def claim_task(task_id: int, tg_id: int, claim_timeout_hours: int = 2) -> Optional[datetime]:
    """Attempt to claim a task for a user.

    If the task is open, it is reserved for the user, a due time is set and
    returned.  If the task is already claimed or completed, returns None.
    """

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM task_instances WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if not row or row["status"] != "open":
            return None
        now = datetime.utcnow()
        due = now + timedelta(hours=claim_timeout_hours)
        cur.execute(
            "UPDATE task_instances SET status = 'reserved', claimed_by = ?, claimed_at = ?, due_at = ? WHERE id = ?",
            (tg_id, now.isoformat(), due.isoformat(), task_id),
        )
        conn.commit()
        return due


def complete_task(task_id: int, tg_id: int) -> bool:
    """Mark a task as completed by the specified user.

    Awards the user the base points for the task.  Returns True if the update
    succeeded, False otherwise (e.g. wrong user or wrong status).
    """

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT status, claimed_by, template_id FROM task_instances WHERE id = ?",
            (task_id,),
        )
        row = cur.fetchone()
        if not row or row["status"] != "reserved" or row["claimed_by"] != tg_id:
            return False
        # Fetch base points
        cur.execute(
            "SELECT base_points FROM task_templates WHERE id = ?",
            (row["template_id"],),
        )
        bp = cur.fetchone()["base_points"]
        # Update task status
        cur.execute(
            "UPDATE task_instances SET status = 'completed' WHERE id = ?",
            (task_id,),
        )
        # Add score to user
        cur.execute(
            "UPDATE users SET score = score + ? WHERE tg_id = ?",
            (bp, tg_id),
        )
        conn.commit()
        return True


def miss_task(task_id: int) -> Optional[Tuple[int, int]]:
    """Handle a missed task deadline.

    If the task is still reserved after its deadline, revert it to open and
    apply the penalty to the user who claimed it.  Returns a tuple
    `(user_tg_id, penalty)` if a penalty was applied, or None otherwise.
    """

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT status, claimed_by, template_id FROM task_instances WHERE id = ?",
            (task_id,),
        )
        row = cur.fetchone()
        if not row or row["status"] != "reserved":
            return None
        user_id = row["claimed_by"]
        template_id = row["template_id"]
        # Fetch penalty
        cur.execute(
            "SELECT penalty FROM task_templates WHERE id = ?",
            (template_id,),
        )
        penalty = cur.fetchone()["penalty"]
        # Apply penalty
        cur.execute(
            "UPDATE users SET score = score - ? WHERE tg_id = ?",
            (penalty, user_id),
        )
        # Reopen task
        cur.execute(
            "UPDATE task_instances SET status = 'open', claimed_by = NULL, claimed_at = NULL, due_at = NULL WHERE id = ?",
            (task_id,),
        )
        conn.commit()
        return user_id, penalty


def generate_tasks_for_day(day: date) -> None:
    """Generate task instances for the given day.

    For each task template, create a task instance if one does not already exist
    for that day and if the template frequency matches the day.  Supported
    frequencies are 'daily', 'weekly', 'weekend' and 'weekday'.
    """

    with get_db_connection() as conn:
        cur = conn.cursor()
        # Fetch templates
        cur.execute("SELECT id, frequency FROM task_templates")
        templates = cur.fetchall()
        for tpl in templates:
            tpl_id = tpl["id"]
            freq = tpl["frequency"]
            if not _should_generate_on(freq, day):
                continue
            # Check if instance exists
            cur.execute(
                "SELECT id FROM task_instances WHERE template_id = ? AND task_date = ?",
                (tpl_id, day.isoformat()),
            )
            if cur.fetchone():
                continue
            # Create new instance
            cur.execute(
                "INSERT INTO task_instances (template_id, task_date, status, announced) VALUES (?, ?, 'open', 0)",
                (tpl_id, day.isoformat()),
            )
        conn.commit()


def _should_generate_on(frequency: str, day: date) -> bool:
    """Return True if a template with the given frequency should run on the day."""

    weekday = day.weekday()  # Monday=0
    if frequency == "daily":
        return True
    if frequency == "weekday":
        return weekday < 5
    if frequency == "weekend":
        return weekday >= 5
    if frequency == "weekly":
        # Monday is default weekly day
        return weekday == 0
    return False


def list_leaderboard(limit: int = 10) -> List[sqlite3.Row]:
    """Return the top users sorted by score descending."""

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT tg_id, name, score FROM users ORDER BY score DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Telegram bot handlers
# ---------------------------------------------------------------------------

# Claim timeout in hours (can be tuned).  Users must complete tasks within
# this many hours after claiming, otherwise they lose points and the task reopens.
CLAIM_TIMEOUT_HOURS = 2


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command.

    Registers the user in the database and sends a welcome message with a menu
    overview.  If the user starts the bot privately, a menu of commands is
    displayed.  If started in a group chat, only a brief message is shown.
    """

    user = update.effective_user
    if not user:
        return
    get_or_create_user(user.id, user.full_name or user.username or str(user.id))
    if update.message:
        await update.message.reply_text(
            "Привет! Я бот для управления домашними задачами. Используйте /tasks, "
            "/rating или /me, чтобы посмотреть доступные действия."
        )


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List today's open and reserved tasks.

    Sends a message containing the tasks for today.  Each open task includes
    inline buttons to claim it.  Reserved tasks show who has claimed them and
    when they are due.  Completed tasks are omitted.
    """

    if not update.message:
        return
    user = update.effective_user
    rows = list_tasks_for_today()
    if not rows:
        await update.message.reply_text("На сегодня задач нет – все свободны!")
        return
    for row in rows:
        task_id = row["id"]
        title = row["title"]
        status = row["status"]
        claimed_by = row["claimed_by"]
        due_at = row["due_at"]
        base_points = row["base_points"]
        if status == "open":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Беру", callback_data=f"claim:{task_id}")],
            ])
            await update.message.reply_text(
                f"🧹 Задача: {title} (+{base_points} баллов). Нажмите 'Беру', чтобы её выполнить.",
                reply_markup=keyboard,
            )
        elif status == "reserved":
            user_name = "кто-то"
            if claimed_by:
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM users WHERE tg_id = ?", (claimed_by,))
                    r = cur.fetchone()
                    if r:
                        user_name = r["name"]
            due_text = "скоро" if not due_at else datetime.fromisoformat(due_at).strftime("%H:%M")
            if user and claimed_by == user.id:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Готово", callback_data=f"done:{task_id}")]
                ])
            else:
                keyboard = None
            await update.message.reply_text(
                f"⏳ {title} занята {user_name}. Срок: {due_text}.",
                reply_markup=keyboard,
            )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the leaderboard sorted by score.

    Displays the top users with their scores.  If no one has points yet, a
    message is shown encouraging users to complete tasks.
    """

    if not update.message:
        return
    rows = list_leaderboard(10)
    if not rows:
        await update.message.reply_text("Пока нет участников.")
        return
    text_lines = ["🏆 Таблица лидеров:"]
    for idx, row in enumerate(rows, start=1):
        text_lines.append(f"{idx}. {row['name']}: {row['score']} баллов")
    await update.message.reply_text("\n".join(text_lines))


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current user's score."""

    user = update.effective_user
    if not user:
        return
    if not update.message:
        return
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT score FROM users WHERE tg_id = ?", (user.id,))
        row = cur.fetchone()
        score = row["score"] if row else 0
    await update.message.reply_text(f"У вас {score} баллов.")


async def claim_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a callback query when a user clicks 'Беру'.

    Attempts to reserve the task for the user and schedules a deadline job.  If
    the task is already taken, the user is informed.  The deadline is
    scheduled using the job queue as a one‑time job.
    """

    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data
    if not data.startswith("claim:"):
        return
    task_id = int(data.split(":", 1)[1])
    user = query.from_user
    due = claim_task(task_id, user.id, claim_timeout_hours=CLAIM_TIMEOUT_HOURS)
    if not due:
        await query.edit_message_text("Эта задача уже взята другим участником.")
        return
    # Schedule deadline check
    context.job_queue.run_once(
        miss_deadline_job,
        when=timedelta(hours=CLAIM_TIMEOUT_HOURS),
        data={"task_id": task_id},
        name=f"deadline_{task_id}",
    )
    # Edit the message to reflect that the task has been taken
    due_time_local = due.astimezone().strftime("%H:%M") if due.tzinfo else due.strftime("%H:%M")
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Готово", callback_data=f"done:{task_id}")]]
    )
    await query.edit_message_text(
        f"✅ {user.first_name} взял задачу. Срок выполнения: {due_time_local}.",
        reply_markup=keyboard,
    )


async def complete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a callback query when a user marks a task as done."""

    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data
    if not data.startswith("done:"):
        return
    task_id = int(data.split(":", 1)[1])
    user = query.from_user
    task = get_task_instance(task_id)
    if not task or task["status"] != "reserved" or task["claimed_by"] != user.id:
        await query.edit_message_text("Эту задачу нельзя завершить.")
        return
    if not complete_task(task_id, user.id):
        await query.edit_message_text("Не удалось завершить задачу. Попробуйте позже.")
        return
    # Cancel deadline job if it exists
    for job in context.job_queue.get_jobs_by_name(f"deadline_{task_id}"):
        job.schedule_removal()
    await query.edit_message_text(
        f"🎉 {task['title']} выполнена! Вы получили {task['base_points']} баллов."
    )
    family_chat_id = context.bot_data.get("family_chat_id")
    if family_chat_id:
        try:
            await context.bot.send_message(
                chat_id=family_chat_id,
                text=f"{user.first_name} завершил(а) задачу «{task['title']}» и получил(а) {task['base_points']} баллов!"
            )
        except Exception:
            pass


async def miss_deadline_job(context: CallbackContext) -> None:
    """Job function called when a task deadline passes.

    If the task is still reserved, it reopens the task and applies a penalty.
    A notification is sent to the group and to the user who missed the task.
    """

    job_data = context.job.data or {}
    task_id = job_data.get("task_id")
    if task_id is None:
        return
    result = miss_task(task_id)
    if not result:
        return
    user_id, penalty = result
    # Send messages: one to the user, one to the group
    if penalty > 0:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ Срок задачи истёк. Вы потеряли {penalty} баллов, и задача снова доступна."
            )
        except Exception:
            # ignore errors when messaging the user
            pass
    # Announce in group chat
    family_chat_id = context.bot_data.get("family_chat_id")
    if family_chat_id:
        await context.bot.send_message(
            chat_id=family_chat_id,
            text="Задача снова доступна, потому что исполнитель не выполнил её вовремя. Используйте /tasks, чтобы посмотреть задачи."
        )


async def generate_daily_tasks_job(context: CallbackContext) -> None:
    """Job function that generates today’s tasks.

    Runs every morning.  Uses the templates table to create new task instances
    for the current date.  If tasks already exist for today, nothing happens.
    """

    today = date.today()
    generate_tasks_for_day(today)
    logging.getLogger(__name__).info("Generated tasks for %s", today)


async def announce_tasks_job(context: CallbackContext) -> None:
    """Job function that announces unannounced tasks to the group.

    Sends a message for each open, unannounced task to the family chat with a
    'Беру' button.  Marks tasks as announced to avoid duplicate announcements.
    """

    family_chat_id = context.bot_data.get("family_chat_id")
    if not family_chat_id:
        logging.getLogger(__name__).warning("FAMILY_CHAT_ID not set; cannot announce tasks")
        return
    rows = list_tasks_for_today()
    for row in rows:
        if row["status"] != "open":
            continue
        task_id = row["id"]
        title = row["title"]
        base_points = row["base_points"]
        # Check if announced
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT announced FROM task_instances WHERE id = ?", (task_id,))
            r = cur.fetchone()
            if not r or r["announced"]:
                continue
            # Mark as announced
            cur.execute("UPDATE task_instances SET announced = 1 WHERE id = ?", (task_id,))
            conn.commit()
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Беру", callback_data=f"claim:{task_id}")]]
        )
        try:
            await context.bot.send_message(
                chat_id=family_chat_id,
                text=f"🧹 Новая задача: {title} (+{base_points} баллов). Нажмите 'Беру', чтобы её выполнить.",
                reply_markup=keyboard,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("Failed to announce task %s: %s", task_id, exc)


async def addtask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to add a new task template.

    Usage: /addtask <frequency>;<title>;<points>;<penalty>;<description>
    Example: /addtask daily;Мыть посуду;10;5;Помыть всю посуду после обеда

    Only users whose ID is listed in ADMIN_IDS may use this command.
    """

    if not update.message:
        return
    user = update.effective_user
    admin_ids = context.bot_data.get("admin_ids", set())
    if not user or user.id not in admin_ids:
        await update.message.reply_text("У вас нет прав добавлять задания.")
        return
    if not context.args:
        await update.message.reply_text(
            "Использование: /addtask <frequency>;<title>;<points>;<penalty>;<description>"
        )
        return
    arg_str = " ".join(context.args)
    parts = [p.strip() for p in arg_str.split(";")]
    if len(parts) < 4:
        await update.message.reply_text(
            "Недостаточно параметров. Формат: <frequency>;<title>;<points>;<penalty>;<description>"
        )
        return
    frequency, title, points_str, penalty_str = parts[:4]
    description = parts[4] if len(parts) > 4 else ""
    frequency = frequency.lower()
    if frequency not in {"daily", "weekly", "weekday", "weekend"}:
        await update.message.reply_text(
            "Частота должна быть одной из: daily, weekly, weekday, weekend"
        )
        return
    try:
        base_points = int(points_str)
        penalty = int(penalty_str)
    except ValueError:
        await update.message.reply_text("Бонусы и штрафы должны быть числами.")
        return
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO task_templates (title, description, frequency, base_points, penalty) VALUES (?, ?, ?, ?, ?)",
            (title, description, frequency, base_points, penalty),
        )
        conn.commit()
    await update.message.reply_text(f"Добавлена задача '{title}' с частотой {frequency}.")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unknown commands."""

    if update.message:
        await update.message.reply_text("Неизвестная команда. Используйте /tasks, /rating или /me.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the bot, schedule jobs and register handlers."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    init_db()
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN environment variable is required")
    # Build the application
    application: Application = ApplicationBuilder().token(bot_token).build()
    # Store group chat id and admin IDs in bot_data for easy access
    family_chat_id = os.environ.get("FAMILY_CHAT_ID")
    if family_chat_id:
        try:
            application.bot_data["family_chat_id"] = int(family_chat_id)
        except ValueError:
            logging.getLogger(__name__).warning("FAMILY_CHAT_ID must be an integer")
    admin_str = os.environ.get("ADMIN_IDS", "")
    admin_ids = set()
    for part in admin_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            admin_ids.add(int(part))
        except ValueError:
            continue
    application.bot_data["admin_ids"] = admin_ids
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler(["tasks", "task", "today"], tasks_command))
    application.add_handler(CommandHandler(["rating", "leaderboard"], leaderboard_command))
    application.add_handler(CommandHandler("me", me_command))
    application.add_handler(CommandHandler("addtask", addtask_command))
    # Callback for claiming tasks
    application.add_handler(CallbackQueryHandler(claim_callback, pattern=r"^claim:\d+$"))
    application.add_handler(CallbackQueryHandler(complete_callback, pattern=r"^done:\d+$"))
    # Unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    # Schedule daily jobs
    # Generate tasks every day at midnight (server time)
    application.job_queue.run_daily(generate_daily_tasks_job, time(hour=0, minute=0))
    # Announce tasks every day at 12:00 local time – the default timezone is UTC.
    application.job_queue.run_daily(announce_tasks_job, time(hour=12, minute=0))
    # Start the bot
    application.run_polling()


if __name__ == "__main__":
    main()
