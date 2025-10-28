# Home Bot — Domestic Task Manager for Telegram

A household management bot built with **aiogram 3**, **SQLAlchemy 2**, and **APScheduler 3**. The bot runs daily task races, photo verification with voting, score tracking, and admin tools that match the specification provided in the project brief.

## Key Features
- 🔔 Daily and weekly task generation at 04:00 (local time) with quiet-hour awareness.
- 🧹 Task race with "take now" and up to two 30‑minute deferrals (−20%/−40% reward).
- 📸 Photo reports routed to peers for voting (auto-finalisation after 15 minutes if only one vote).
- 📉 Automatic penalties when nobody claims a task by the template deadline or when SLA is missed.
- ♻️ Re-announcements every ~2 hours until a task is taken, observing quiet hours.
- 🧾 Score ledger with `/balance`, `/history`, `/rating`, and monthly reset flow.
- ⚖️ Dispute tracking with `/disputes` and `/resolve_dispute` admin actions.
- 🤖 AI-контроллер, который динамически корректирует вознаграждения в зависимости от истории задач.
- 🛠 Admin commands for manual announcements, template seeding, dispute resolution, and season resets.

## Environment & Configuration
- Python 3.11 is required. The repository ships with `.python-version` and `runtime.txt` to keep Koyeb and local tooling aligned.
- Default database: `sqlite:///data.db` stored in the working directory. Override with `DATABASE_URL` (e.g. PostgreSQL) if needed.
- Quiet hours and timezone are configurable; announcements are deferred to the first available slot outside quiet hours.
- `ADMIN_IDS` accepts a single int, CSV string, or JSON list — parsing is handled in `home_bot/config.py`.

### Required environment variables
| Variable | Description |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token. The bot refuses to start if empty. |
| `ADMIN_IDS` | Admin Telegram user IDs (int / CSV / JSON). |
| `TZ` | IANA timezone (default `Europe/Warsaw`). |
| `QUIET_HOURS` | Quiet window like `23:00-08:00`. |
| `DATABASE_URL` | Optional; defaults to `sqlite:///data.db`. |

Additional optional variable: `TZ` defaults to `Europe/Warsaw`, matching the specification.

## Commands & Menus
### User commands
- `/start` — register and get onboarding tips.
- `/menu` — show reply keyboard with shortcuts.
- `/tasks` — list open/reserved tasks.
- `/rating` — household leaderboard.
- `/balance` — personal score.
- `/history` — last 20 score events.
- `/help` — summary of commands.

Inline menu (`/menu`):
```
📋 Задания
🏆 Баланс
📜 История
ℹ️ Помощь
⚙️ AI Настройки (только для админов)
```

### Admin commands
- `/announce` — force re-announce the oldest open task.
- `/add_task code;Title;points;frequency;max_per_day;sla;claim_timeout;kind;penalty` — add a template.
- `/disputes` — list unresolved disputes.
- `/resolve_dispute <id> <approve|reject> <note>` — close a dispute and optionally grant reward.
- `/ai_stats` — show adaptive reward coefficients per user.
- `/ai_config penalty=0.05 bonus=0.02` — tweak AI reward parameters.
- `/end_month` — announce winner and reset seasonal scores.

## Behaviour Overview
1. **Task generation** — 04:00 job creates instances for the day/week based on template frequency, then broadcasts announcements with inline buttons (take now/defer).
2. **Claim timeout** — if nobody claims before `claim_timeout_minutes`, everyone receives the template penalty and the bot schedules a re-announcement after ~2 hours. This loop repeats until the task is taken.
3. **Deferrals & SLA** — deferring adds 30 minutes per click (max twice) and reduces reward by 20%/40%. Missing the SLA results in an immediate double penalty and the task reopens.
4. **Reports & voting** — performers send a photo; the bot forwards it to two peers for `/vote` buttons. Two votes end the review immediately; otherwise a 15-minute timer finalises with the first vote.
5. **Score ledger** — every award or penalty creates a `ScoreEvent` entry. `/history` shows the last 20 records; `/rating` sorts by current balance.
6. **Disputes** — negative or conflicting votes open a `Dispute` entry for admins. Resolutions are logged and, if approved, points are added retroactively.
7. **Quiet hours** — any scheduled announcement that falls within quiet hours is delayed to the first allowed minute outside the window.

## Local Development
```bash
pip install -r requirements.txt
make run   # or python -m home_bot.main
```

The `Makefile` includes a `run` target for convenience. Database tables and default templates are auto-created on startup.

## Deployment on Koyeb
1. Ensure the repository contains `Procfile` with `worker: python -m home_bot.main` (already provided).
2. In the Koyeb service:
   - Leave the Build command empty (Buildpack takes care of deps).
   - Set Run command to `python -m home_bot.main` or rely on the Procfile.
   - Configure environment variables as described above.
3. SQLite is stored in the working directory; for production use, supply a managed Postgres connection string via `DATABASE_URL`.

## AI Reward Controller
The adaptive reward engine lives in `home_bot/services/ai_controller.py`. It analyses how many tasks each family member завершил или пропустил и вычисляет коэффициент вознаграждения. При генерации задач база (`base_points`) умножается на средний коэффициент, а результат сохраняется как `effective_points`. Команды `/ai_stats` и `/ai_config` позволяют администраторам просматривать историю и настраивать параметры (`penalty_step`, `bonus_step`, минимальный/максимальный коэффициенты и значение по умолчанию).

При отклонении отчёта счётчик `attempts` увеличивается, задача остаётся в статусе "в работе" с прогрессом 50 %, а после подтверждения прогресс фиксируется на 100 %. Обзор задач показывает текущий прогресс, количество попыток и актуальные баллы.

## Acceptance Checklist
- `/start` shows the onboarding guide and keyboard.
- Claim timeouts penalise everyone and re-announce.
- Deferrals apply −20%/−40% reward, logged in the final score event.
- SLA misses trigger double penalties and reopen the task.
- Single vote verdicts auto-finalise after 15 minutes.
- `/rating` and `/history` reflect live data.
- `/end_month` announces the season winner and resets balances.
- `/ai_stats` and `/ai_config` expose and tweak adaptive reward settings.

Happy housekeeping! 🧼
