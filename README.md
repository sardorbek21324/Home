# Home Tasks Bot

A lightweight Telegram bot that helps families coordinate household chores. The bot is built with [python-telegram-bot 20](https://docs.python-telegram-bot.org/) and keeps state in a small SQLite database so it can be deployed anywhere a single Python process can run.

## Features
- 📆 Generates daily task instances from reusable templates stored in the database.
- 🔔 Announces open tasks to a family chat with inline "Беру" buttons for quick claiming.
- ⏳ Tracks claim deadlines; missed deadlines reopen the task and apply a penalty.
- 🧮 Awards points for completed chores and tracks a simple leaderboard.
- 🔐 Supports an `/addtask` admin command for managing task templates on the fly.

## Requirements
- Python 3.11+
- Telegram bot token created via [@BotFather](https://t.me/BotFather)
- [`python-telegram-bot` >= 20,<21](https://docs.python-telegram-bot.org/)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration
Set the following environment variables before launching the bot:

| Variable | Description |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token (required). |
| `FAMILY_CHAT_ID` | Telegram chat ID for group announcements (optional). |
| `ADMIN_IDS` | Comma-separated Telegram user IDs that may run `/addtask`. |
| `DB_PATH` | Optional path to the SQLite database file (defaults to `home_tasks.db`). |

Example:

```bash
export BOT_TOKEN="123456:ABC..."
export FAMILY_CHAT_ID="-1001234567890"
export ADMIN_IDS="12345,67890"
```

## Running locally
Generate templates and start the polling loop:

```bash
python home_tasks_bot.py
```

On first run the bot creates the SQLite schema automatically and schedules two background jobs:

1. **Midnight** — generate today’s task instances from templates.
2. **12:00** — announce unclaimed tasks to the configured family chat.

## Commands
- `/start` — register and receive a short onboarding message.
- `/tasks` — list today’s tasks and let users claim available ones.
- `/rating` — show the top scorers.
- `/me` — show personal points.
- `/addtask frequency;title;points;penalty;description` — create a new recurring template (admins only).

Inline buttons are provided for claiming tasks directly from announcements. Deadlines and penalties are managed automatically via `JobQueue` timers.

## Deployment
The repository includes a `Procfile` that can be used with platforms such as Heroku or Koyeb. Set the environment variables shown above and start the worker process:

```bash
python home_tasks_bot.py
```

Because the bot relies on SQLite by default, ensure the working directory is persisted across restarts if you need long-term history. You can also point `DB_PATH` to another location (e.g., a mounted volume).

Happy housekeeping! 🧼
