"""Project settings helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    """Provide default SQLite path inside the working directory."""

    db_path = Path("data.db").resolve()
    return f"sqlite:///{db_path}"


def _parse_ids(env_value: str | None, fallback: list[int]) -> list[int]:
    if not env_value:
        return fallback
    s = env_value.strip()
    if not s:
        return fallback
    try:
        if s.startswith("["):
            arr = json.loads(s)
            return [int(x) for x in arr]
        return [int(x) for x in s.split(",") if x.strip()]
    except Exception:
        return fallback


ADMIN_IDS_DEFAULT = [133405512]
FAMILY_IDS_DEFAULT = [133405512, 310837917, 389957226]


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment."""

    BOT_TOKEN: str
    OPENAI_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "OPENAI_KEY"),
    )
    OPENAI_MODEL: str = "gpt-4o-mini"
    DATABASE_URL: str = Field(default_factory=_default_database_url)
    ANNOUNCE_CUTOFF_MINUTES: int = 10
    TZ: str = "Europe/Warsaw"
    QUIET_HOURS: str = "23:00-08:00"

    ADMIN_IDS_ENV: str | None = Field(default_factory=lambda: os.getenv("ADMIN_IDS"))
    FAMILY_IDS_ENV: str | None = Field(default_factory=lambda: os.getenv("FAMILY_IDS"))

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        case_sensitive=False,
        protected_namespaces=(),
    )

    @property
    def ADMIN_IDS(self) -> list[int]:
        return _parse_ids(self.ADMIN_IDS_ENV, ADMIN_IDS_DEFAULT)

    @property
    def FAMILY_IDS(self) -> list[int]:
        return _parse_ids(self.FAMILY_IDS_ENV, FAMILY_IDS_DEFAULT)


settings = Settings()


def get_family_user_ids() -> List[int]:
    """Return configured Telegram user ids for the family circle."""

    return list(settings.FAMILY_IDS)
