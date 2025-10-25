from __future__ import annotations

import json
import logging

from ..config import settings

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


log = logging.getLogger(__name__)

_client: OpenAI | None = None


def ai_enabled() -> bool:
    """Return True if OpenAI integration is configured."""

    return bool(settings.OPENAI_API_KEY and OpenAI is not None)


def _cli() -> OpenAI | None:
    global _client
    if not ai_enabled():
        return None
    if _client is None:
        try:
            _client = OpenAI(api_key=settings.OPENAI_API_KEY)
        except Exception as exc:  # pragma: no cover - network
            log.info("OpenAI client init failed: %s", exc)
            _client = None
    return _client


def weekly_patch(summary_json: dict) -> dict:
    client = _cli()
    if client is None:
        log.info("OpenAI disabled; returning empty patch.")
        return {}
    prompt = (
        "You are a balance advisor for a household gamified bot. "
        "Given the weekly aggregate JSON, propose adjustments within corridors: "
        "increase/decrease task points within provided min/max; propose one-day booster events; "
        "and short motivation text. Respond JSON with keys: increase_points, decrease_points, events, message."
    )
    messages = [
        {"role": "system", "content": "Be concise and safe. Do not include PII."},
        {"role": "user", "content": prompt},
        {"role": "user", "content": json.dumps(summary_json)}
    ]
    try:
        res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, temperature=0.4)
        txt = res.choices[0].message.content
        patch = json.loads(txt)
        return patch
    except Exception as exc:  # pragma: no cover - network
        log.info("OpenAI advisor failed: %s", exc)
        return {}


async def draft_announce(template_title: str, points: int, bonus_hint: str) -> str:
    """Generate friendly announce text using OpenAI with fallback."""

    client = _cli()
    default_text = f"🧹 Задача: <b>{template_title}</b> (+{points}). {bonus_hint}"
    if client is None:
        return default_text
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ты короткий мотивационный помощник. Пиши дружелюбно и по делу.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Сформулируй анонс задачи '{template_title}' на +{points} баллов. "
                        "Добавь мотивацию и напомни про бонус первому, но не занимай >160 символов."
                    ),
                },
            ],
            temperature=0.7,
        )
        message = resp.choices[0].message.content or ""
        return message.strip() or default_text
    except Exception as exc:  # pragma: no cover - network
        log.info("OpenAI draft announce failed: %s", exc)
        return default_text
