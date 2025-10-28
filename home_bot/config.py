"""Project settings helpers using Pydantic settings management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    """Provide default SQLite path inside the working directory."""

    db_path = Path("data.db").resolve()
    return f"sqlite:///{db_path}"


def _normalize_ids(value: object, fallback: Sequence[int]) -> list[int]:
    """Parse JSON or comma separated identifiers into a list of ints."""

    if value is None:
        return list(fallback)
    if isinstance(value, str):
        data = value.strip()
        if not data:
            return list(fallback)
        try:
            if data.startswith("["):
                raw = json.loads(data)
            else:
                raw = [part.strip() for part in data.split(",") if part.strip()]
        except json.JSONDecodeError:
            return list(fallback)
        try:
            return [int(item) for item in raw]
        except (TypeError, ValueError):
            return list(fallback)
    if isinstance(value, Iterable):
        try:
            return [int(item) for item in value]
        except (TypeError, ValueError):
            return list(fallback)
    return list(fallback)


ADMIN_IDS_DEFAULT = [133405512]
FAMILY_IDS_DEFAULT = [133405512, 310837917, 389957226]


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        case_sensitive=False,
        protected_namespaces=(),
    )

    bot_token: str = Field(validation_alias=AliasChoices("BOT_TOKEN"))
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "OPENAI_KEY"),
    )
    openai_model: str = Field(default="gpt-4o-mini", validation_alias=AliasChoices("OPENAI_MODEL"))
    database_url: str = Field(default_factory=_default_database_url, validation_alias=AliasChoices("DATABASE_URL"))
    announce_cutoff_minutes: int = Field(default=10, validation_alias=AliasChoices("ANNOUNCE_CUTOFF_MINUTES"))
    tz: str = Field(default="Europe/Warsaw", validation_alias=AliasChoices("TZ"))
    quiet_hours: str = Field(default="23:00-08:00", validation_alias=AliasChoices("QUIET_HOURS"))
    admin_ids: list[int] = Field(
        default_factory=lambda: list(ADMIN_IDS_DEFAULT),
        validation_alias=AliasChoices("ADMIN_IDS"),
    )
    family_ids: list[int] = Field(
        default_factory=lambda: list(FAMILY_IDS_DEFAULT),
        validation_alias=AliasChoices("FAMILY_IDS"),
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> list[int]:
        return _normalize_ids(value, ADMIN_IDS_DEFAULT)

    @field_validator("family_ids", mode="before")
    @classmethod
    def _parse_family_ids(cls, value: object) -> list[int]:
        return _normalize_ids(value, FAMILY_IDS_DEFAULT)

    @property
    def BOT_TOKEN(self) -> str:  # noqa: N802 - legacy compatibility
        return self.bot_token

    @property
    def OPENAI_API_KEY(self) -> str | None:  # noqa: N802 - legacy compatibility
        return self.openai_api_key

    @property
    def OPENAI_MODEL(self) -> str:  # noqa: N802 - legacy compatibility
        return self.openai_model

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802 - legacy compatibility
        return self.database_url

    @property
    def ANNOUNCE_CUTOFF_MINUTES(self) -> int:  # noqa: N802 - legacy compatibility
        return self.announce_cutoff_minutes

    @property
    def TZ(self) -> str:  # noqa: N802 - legacy compatibility
        return self.tz

    @property
    def QUIET_HOURS(self) -> str:  # noqa: N802 - legacy compatibility
        return self.quiet_hours

    @property
    def ADMIN_IDS(self) -> list[int]:  # noqa: N802 - legacy compatibility
        return list(self.admin_ids)

    @property
    def FAMILY_IDS(self) -> list[int]:  # noqa: N802 - legacy compatibility
        return list(self.family_ids)

    def set_admin_ids(self, values: Sequence[int]) -> None:
        self.admin_ids = list(values)

    def set_family_ids(self, values: Sequence[int]) -> None:
        self.family_ids = list(values)


settings = Settings()


def get_family_user_ids() -> list[int]:
    """Return configured Telegram user ids for the family circle."""

    return list(settings.FAMILY_IDS)
