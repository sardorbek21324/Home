"""Utility helpers for resilient Telegram API calls."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, TypeVar

from aiogram import Bot
from aiogram.types import Message

log = logging.getLogger(__name__)


T = TypeVar("T")


async def _with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    description: str,
) -> T | None:
    """Execute ``operation`` with retries and exponential backoff."""

    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - network reliability
            log.warning(
                "Failed to %s (attempt %s/%s): %s",
                description,
                attempt,
                attempts,
                exc,
            )
            if attempt == attempts:
                log.error("Giving up on %s after %s attempts", description, attempts)
                return None
            await asyncio.sleep(base_delay * attempt)
    return None


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    **kwargs: Any,
) -> Message | None:
    """Send a message with retry logic."""

    return await _with_retries(
        lambda: bot.send_message(chat_id, text, **kwargs),
        description="send message",
    )


async def safe_send_photo(
    bot: Bot,
    chat_id: int,
    *,
    photo: str,
    **kwargs: Any,
) -> Message | None:
    """Send a photo with retry logic."""

    return await _with_retries(
        lambda: bot.send_photo(chat_id, photo=photo, **kwargs),
        description="send photo",
    )


async def answer_safe(message: Message, text: str, **kwargs: Any) -> Message | None:
    """Reply to a message using the same retry policy."""

    return await _with_retries(
        lambda: message.answer(text, **kwargs),
        description="answer message",
    )
