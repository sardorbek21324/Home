"""Application configuration using Pydantic settings."""
from __future__ import annotations

from typing import List, Optional
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Centralised configuration for the bot."""

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
