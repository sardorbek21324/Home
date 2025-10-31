from __future__ import annotations

"""Commands related to rating, balances and score history."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..db.models import ScoreEvent, User
from ..db.repo import list_users, session_scope
from ..utils.telegram import answer_safe
from ..utils.text import escape_html


router = Router()


def _get_user(session, tg_id: int) -> User | None:
    return session.query(User).filter(User.tg_id == tg_id).one_or_none()


def _format_balance(user: User) -> str:
    return f"Ваш текущий баланс: {user.score} баллов."


def _format_history(rows: list[ScoreEvent]) -> str:
    if not rows:
        return "История пуста."
    lines = ["📅 Последние события"]
    for event in rows:
        sign = "➕" if event.delta >= 0 else "➖"
        reason = escape_html(event.reason)
        lines.append(
            f"{event.created_at:%d.%m %H:%M} — {sign}{abs(event.delta)} за {reason}"
        )
    return "\n".join(lines)


def build_balance_text(tg_id: int) -> str:
    with session_scope() as session:
        user = _get_user(session, tg_id)
        if not user:
            return "Сначала нажми /start, чтобы зарегистрироваться."
        return _format_balance(user)


def build_history_text(tg_id: int) -> str:
    with session_scope() as session:
        user = _get_user(session, tg_id)
        if not user:
            return "Сначала нажми /start, чтобы зарегистрироваться."
        rows = (
            session.query(ScoreEvent)
            .filter(ScoreEvent.user_id == user.id)
            .order_by(ScoreEvent.created_at.desc())
            .limit(20)
            .all()
        )
        return _format_history(rows)


@router.message(Command("rating"))
async def show_rating(message: Message) -> None:
    with session_scope() as session:
        entries = [
            (escape_html(user.username or user.name or str(user.tg_id)), user.score)
            for user in list_users(session)
        ]
    if not entries:
        await answer_safe(message, "Пока нет участников.")
        return

    lines = ["🏆 Таблица лидеров"]
    for index, (name, score_value) in enumerate(sorted(entries, key=lambda item: item[1], reverse=True), start=1):
        lines.append(f"{index}. {name} — {score_value} баллов")
    await answer_safe(message, "\n".join(lines))


@router.message(Command("balance", "me"))
async def show_balance(message: Message) -> None:
    if message.from_user is None:
        return
    await answer_safe(message, build_balance_text(message.from_user.id))


@router.message(Command("history"))
async def history(message: Message) -> None:
    if message.from_user is None:
        return
    await answer_safe(message, build_history_text(message.from_user.id))
