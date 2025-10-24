from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field

# Prefer static local settings so user edits only one file.
_defaults = {}
try:
    from .local_settings import BOT_TOKEN, OPENAI_API_KEY, DATABASE_URL, ADMIN_IDS, TZ, QUIET_HOURS
    _defaults = {
        "BOT_TOKEN": BOT_TOKEN,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "DATABASE_URL": DATABASE_URL,
        "ADMIN_IDS": ADMIN_IDS,
        "TZ": TZ,
        "QUIET_HOURS": QUIET_HOURS,
    }
except Exception:
    # If local_settings.py missing, fall back to env variables (still supported).
    _defaults = {}

class Settings(BaseSettings):
    BOT_TOKEN: str = _defaults.get("BOT_TOKEN", "")
    OPENAI_API_KEY: str | None = _defaults.get("OPENAI_API_KEY", None)
    DATABASE_URL: str = _defaults.get("DATABASE_URL", "sqlite:///data.db")
    ADMIN_IDS: List[int] = Field(default_factory=lambda: _defaults.get("ADMIN_IDS", []))
    TZ: str = _defaults.get("TZ", "Europe/Warsaw")
    QUIET_HOURS: str = _defaults.get("QUIET_HOURS", "23:00-08:00")

settings = Settings()

# Friendly guardrail: nudge user to paste token if left blank
if not settings.BOT_TOKEN or settings.BOT_TOKEN == "PASTE_TELEGRAM_BOT_TOKEN_HERE":
    raise RuntimeError("Please open home_bot/local_settings.py and paste your BOT_TOKEN.")
