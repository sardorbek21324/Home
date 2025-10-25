"""Project settings helpers."""

from __future__ import annotations

import json
from typing import Any, Iterable

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _coerce_admin_ids(value: Any) -> list[int]:
    """Convert supported representations of admin ids to a list of ints."""

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
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"ADMIN_IDS JSON parse error: {exc}") from exc
        return _coerce_admin_ids(parsed)

    # allow comma separated values
    if "," in text:
        return [int(chunk.strip()) for chunk in text.split(",") if chunk.strip()]

    return [int(text)]


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment."""

    BOT_TOKEN: str
    OPENAI_API_KEY: str | None = None
    DATABASE_URL: str = "sqlite:///data.db"
    ADMIN_IDS: list[int] = []
    TZ: str = "Europe/Moscow"
    QUIET_HOURS: str = "23:00-08:00"

    model_config = SettingsConfigDict(env_prefix="", env_file=None, case_sensitive=False)

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def _validate_admin_ids(cls, value: Any) -> list[int]:
        return _coerce_admin_ids(value)

    @field_validator("BOT_TOKEN")
    @classmethod
    def _ensure_bot_token(cls, value: str) -> str:
        if not value:
            raise ValueError("BOT_TOKEN environment variable is required")
        return value


settings = Settings()  # type: ignore[arg-type]
