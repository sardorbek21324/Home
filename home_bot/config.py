"""Project settings helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    """Provide default SQLite path inside the working directory."""

    db_path = Path("data.db").resolve()
    return f"sqlite:///{db_path}"


def _coerce_ids(value: Any) -> list[int]:
    """Convert supported representations of ids to a list of ints."""

    if value is None or value == "":
        return []

    if isinstance(value, int):
        return [value]

    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        result: list[int] = []
        for item in value:
            if item is None or item == "":
                continue
            result.append(int(item))
        return result

    text = str(value).strip()
    if not text:
        return []

    # Support values such as "[1,2]" or "1,2" from platform envs.
    text = text.replace("[", "").replace("]", "")
    chunks = [chunk.strip() for chunk in text.split(",") if chunk.strip()]
    return [int(chunk) for chunk in chunks]


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment."""

    BOT_TOKEN: str
    OPENAI_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_KEY", "OPENAI_API_KEY"),
    )
    DATABASE_URL: str = Field(default_factory=_default_database_url)
    ADMIN_IDS: list[int] = Field(default_factory=list)
    FAMILY_IDS: list[int] = Field(default_factory=list)
    ANNOUNCE_CUTOFF_MINUTES: int = 10
    TZ: str = "Europe/Warsaw"
    QUIET_HOURS: str = "23:00-08:00"

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", case_sensitive=False)

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def _validate_admin_ids(cls, value: Any) -> list[int]:
        return _coerce_ids(value)

    @field_validator("FAMILY_IDS", mode="before")
    @classmethod
    def _validate_family_ids(cls, value: Any) -> list[int]:
        return _coerce_ids(value)

    @field_validator("BOT_TOKEN")
    @classmethod
    def _ensure_bot_token(cls, value: str) -> str:
        if not value:
            raise ValueError("BOT_TOKEN environment variable is required")
        return value


settings = Settings()


def get_family_user_ids() -> List[int]:
    """Return configured Telegram user ids for the family circle."""

    return list(settings.FAMILY_IDS)
