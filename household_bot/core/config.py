"""Application configuration using Pydantic settings."""
from __future__ import annotations

import json
from typing import Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import (
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
)


class _FlexibleEnvSettingsSource(EnvSettingsSource):
    """Environment source that tolerates non-JSON list representations."""

    def decode_complex_value(
        self, field_name: str, field: FieldInfo, value: Any
    ) -> Any:
        """Fallback to returning the raw value if JSON decoding fails.

        Pydantic tries to decode complex values (like lists) as JSON before
        validators are executed. For ``PARTICIPANT_IDS`` we want to allow plain
        comma-separated strings (``"1,2,3"``). By catching ``JSONDecodeError``
        and returning the raw string we give our field validator a chance to
        normalise it.
        """

        if field_name == "PARTICIPANT_IDS" and isinstance(value, str):
            try:
                return super().decode_complex_value(field_name, field, value)
            except ValueError:
                return value

        return super().decode_complex_value(field_name, field, value)


class _FlexibleDotEnvSettingsSource(DotEnvSettingsSource, _FlexibleEnvSettingsSource):
    """Dotenv source sharing the fallback behaviour."""

    pass


class Settings(BaseSettings):
    """Centralised configuration for the bot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Inject custom sources that keep participant IDs flexible."""

        env_prefix = cls.model_config.get("env_prefix")
        env_nested_delimiter = cls.model_config.get("env_nested_delimiter")
        env_file = cls.model_config.get("env_file")
        env_file_encoding = cls.model_config.get("env_file_encoding")

        custom_env = _FlexibleEnvSettingsSource(
            settings_cls,
            env_prefix=env_prefix,
            env_nested_delimiter=env_nested_delimiter,
        )
        custom_dotenv = _FlexibleDotEnvSettingsSource(
            settings_cls,
            env_file=env_file,
            env_file_encoding=env_file_encoding,
            env_prefix=env_prefix,
            env_nested_delimiter=env_nested_delimiter,
        )

        return init_settings, custom_env, custom_dotenv, file_secret_settings

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
