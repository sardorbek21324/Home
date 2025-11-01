"""Application configuration using Pydantic settings."""
from __future__ import annotations

import json
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _tolerant_json_loads(value: Any) -> Any:
    """Return JSON-decoded value but fall back to the original input.

    Pydantic's settings sources attempt to JSON-decode complex types such as
    lists when reading from environment variables. For ``PARTICIPANT_IDS`` we
    support simple comma-separated strings (e.g. ``"1,2,3"``). When such a
    string is supplied, Pydantic's default ``json.loads`` invocation raises a
    ``JSONDecodeError`` before our validators run. To keep backwards
    compatibility, we catch that error here and return the raw value so that it
    can be handled by the validator below.
    """

    if isinstance(value, (bytes, bytearray)):
        value = value.decode()

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    return value


class Settings(BaseSettings):
    """Centralised configuration for the bot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        json_loads=_tolerant_json_loads,
    )

    TELEGRAM_TOKEN: str
    ADMIN_ID: int = 133405512
    PARTICIPANT_IDS: List[int] = Field(
        default_factory=lambda: [133405512, 310837917, 389957226]
    )
    GROUP_CHAT_ID: int
    REPORTS_CHAT_ID: Optional[int] = None

    DATABASE_URL: str = "postgresql+asyncpg://user:password@db:5432/household"

    TIMEZONE: ZoneInfo = Field(default_factory=lambda: ZoneInfo("Europe/Amsterdam"))

    GROCERY_DAY: int = 5

    @field_validator("PARTICIPANT_IDS", mode="before")
    @classmethod
    def parse_participant_ids(cls, value: object) -> object:
        """Allow comma-separated strings for participant IDs.

        When sourced from the environment, ``PARTICIPANT_IDS`` may be supplied as a
        comma-separated string (e.g. ``"1,2,3"``). Pydantic expects JSON for list
        fields, so we normalise the string into a list of integers before normal
        parsing. If the value is already a list or cannot be interpreted, we return
        it unchanged and defer validation to Pydantic.
        """

        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return []

            try:
                parsed = json.loads(stripped_value)
            except json.JSONDecodeError:
                parsed = [item.strip() for item in stripped_value.split(",")]
            else:
                if not isinstance(parsed, list):
                    return parsed

            return [int(item) for item in parsed if item]

        return value

settings = Settings()
