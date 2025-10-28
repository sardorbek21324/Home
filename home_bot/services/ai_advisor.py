"""Safe wrapper around OpenAI Async client for household advice."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from ..config import settings

try:  # pragma: no cover - optional dependency guard
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[misc,assignment]


log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


@dataclass(slots=True)
class Advice:
    title: str
    text: str


class AIAdvisor:
    """Safe async wrapper around the OpenAI SDK."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._model = model or settings.openai_model
        self._timeout = timeout
        self._client: AsyncOpenAI | None = None
        self._enabled = bool(self._api_key and AsyncOpenAI is not None)

    def _get_client(self) -> AsyncOpenAI | None:
        if not self._enabled or not AsyncOpenAI:
            return None
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)
        return self._client

    async def healthcheck(self) -> str:
        """Ping OpenAI with a lightweight request."""

        if AsyncOpenAI is None:
            return "ошибка — SDKNotInstalled"
        if not self._api_key:
            return "ошибка — MissingAPIKey"

        client = self._get_client()
        if client is None:
            return "ошибка — Disabled"

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": "You are a healthcheck."},
                        {"role": "user", "content": "echo ok"},
                    ],
                    max_tokens=4,
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            return "ошибка — TimeoutError"
        except Exception as exc:  # pragma: no cover - depends on network
            return f"ошибка — {exc.__class__.__name__}"

        if not response.choices:
            return "ошибка — EmptyResponse"
        message = response.choices[0].message.content or ""
        return "ok" if "ok" in message.lower() else "ошибка — UnexpectedContent"

    async def suggest_daily_focus(self, context: str) -> Advice:
        """Generate a short focus suggestion for the day."""

        fallback = Advice(
            title="Совет дня",
            text="ИИ недоступен. Следуем плану задач на сегодня.",
        )
        client = self._get_client()
        if client is None:
            return fallback

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Ты — семейный ассистент по домашним делам. "
                                "Сформулируй 1-2 приоритета на сегодня кратко."
                            ),
                        },
                        {"role": "user", "content": context},
                    ],
                    temperature=0.4,
                    max_tokens=200,
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            return Advice(title="Совет дня", text="ИИ долго отвечает. Используем базовый план.")
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("OpenAI request failed: %s", exc)
            return Advice(
                title="Совет дня",
                text=f"ИИ временно недоступен ({exc.__class__.__name__}). Используем план задач.",
            )

        if not response.choices:
            return Advice(title="Совет дня", text="Сегодня работаем по плану.")
        message = (response.choices[0].message.content or "").strip()
        if not message:
            return Advice(title="Совет дня", text="Сегодня работаем по плану.")
        return Advice(title="Совет дня", text=message)
