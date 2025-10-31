"""Application configuration utilities."""
from __future__ import annotations

import logging
import os
from typing import Final

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

TOKEN_ENV_VAR: Final[str] = "TELEGRAM_BOT_TOKEN"


def _load_token_from_env() -> str:
    """Read the bot token from environment variables."""
    load_dotenv()
    token = os.getenv(TOKEN_ENV_VAR)
    if not token:
        logger.error("Environment variable %s is not set", TOKEN_ENV_VAR)
        raise SystemExit(
            f"Set the {TOKEN_ENV_VAR} environment variable with your bot token."
        )
    return token


BOT_TOKEN: Final[str] = _load_token_from_env()
"""Token used to authenticate the Telegram bot."""
