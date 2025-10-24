# Home Bot (Telegram) — Domestic Gamified Assistant

This is a ready-to-run Telegram bot implementing the logic we discussed:
- Tasks (daily/weekly/mini) for 3 household members
- Points & penalties
- Take now / Take later (2 defers) logic
- Photo/video verification with smart timeouts (v3)
- Re-announcements and quiet hours
- Leaderboard and history
- OpenAI advisor (optional) for weekly balance patches & daily digests
- SQLite by default, Postgres optional
- Deployable on Koyeb via GitHub

## Quick Start (Local)

1) Python 3.11+
2) `pip install -r requirements.txt`
3) Create `.env` in repo root:

```
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
OPENAI_API_KEY=YOUR_OPENAI_KEY   # optional
DATABASE_URL=sqlite:///data.db
ADMIN_IDS=123456789              # your telegram user id
TZ=Europe/Warsaw
QUIET_HOURS=23:00-08:00
```

4) Run bot:
```
python -m home_bot.main
```

## Deploy on Koyeb
- Connect GitHub repo
- Build cmd: `pip install -r requirements.txt`
- Run cmd: `python -m home_bot.main`
- Set environment variables as above.

## Commands
- `/start` — register and open menu
- `/rating` — show leaderboard
- `/announce` (admin) — force announce a task now (for testing)
- `/end_month` (admin) — compute winner and reset month (manual trigger)

The scheduler will handle regular announcements & timeouts.

## Notes
- Photos/videos are stored as Telegram file_ids, not binary.
- No PII or media is sent to OpenAI. Only aggregated stats.
- For a full spec, refer to the in-chat specification.
