from __future__ import annotations

import asyncio
import os
from typing import Optional

from pydantic import BaseModel

try:
    # OpenAI SDK v1.x
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


class AIAdvice(BaseModel):
    title: str
    text: str


class AIAdvisor:
    """
    Безопасная обёртка вокруг OpenAI. Если ключа нет или SDK не установлен,
    методы возвращают понятные ошибки, а не падают.
    """

    def __init__(self) -> None:
        self.enabled = bool(_OPENAI_API_KEY and AsyncOpenAI is not None)
        self._client: Optional[AsyncOpenAI] = None
        if self.enabled:
            # Конструируем клиент лениво, в первом вызове, чтобы не падать при импорте
            self._client = AsyncOpenAI(api_key=_OPENAI_API_KEY)

    async def healthcheck(self) -> str:
        """
        Лёгкая проверка доступности OpenAI с таймаутом.
        Возвращает "ok" или строку вида "ошибка — <тип>".
        """
        if not AsyncOpenAI:
            return "ошибка — SDK not installed"
        if not _OPENAI_API_KEY:
            return "ошибка — no API key"

        try:
            assert self._client is not None
            # Мини-запрос с маленьким токен-лимитом
            resp = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a healthcheck."},
                        {"role": "user", "content": "echo ok"},
                    ],
                    max_tokens=5,
                ),
                timeout=15,
            )
            txt = resp.choices[0].message.content if resp.choices else ""
            return "ok" if (txt and "ok" in txt.lower()) else "ошибка — empty response"
        except asyncio.TimeoutError:
            return "ошибка — TimeoutError"
        except Exception as e:
            return f"ошибка — {type(e).__name__}"

    async def suggest_daily_focus(self, context: str) -> AIAdvice:
        """
        Возвращает короткий совет дня для дома и распределения работ.
        При недоступности ИИ — отдаём дефолтный совет без падения.
        """
        if not self.enabled:
            return AIAdvice(
                title="Совет дня",
                text="ИИ недоступен. Используем базовое расписание.",
            )

        try:
            assert self._client is not None
            resp = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Ты — ассистент по домашним делам. "
                                "Дай 1–2 коротких фокус-приоритета на день."
                            ),
                        },
                        {"role": "user", "content": context},
                    ],
                    temperature=0.4,
                    max_tokens=200,
                ),
                timeout=25,
            )
            msg = resp.choices[0].message.content.strip() if resp.choices else ""
            if not msg:
                return AIAdvice(title="Совет дня", text="Сегодня работаем по плану.")
            return AIAdvice(title="Совет дня", text=msg)
        except asyncio.TimeoutError:
            return AIAdvice(title="Совет дня", text="Время ожидания ИИ истекло.")
        except Exception as e:
            return AIAdvice(title="Совет дня", text=f"ИИ недоступен: {type(e).__name__}")
