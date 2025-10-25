from __future__ import annotations

"""Commands related to rating, balances and score history."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..db.models import ScoreEvent, User
from ..db.repo import list_users, session_scope


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
        lines.append(
            f"{event.created_at:%d.%m %H:%M} — {sign}{abs(event.delta)} за {event.reason}"
        )
    return "\n".join(lines)


@router.message(Command("rating"))
async def show_rating(message: Message) -> None:
    with session_scope() as session:
        entries = [(user.username or user.name or str(user.tg_id), user.score) for user in list_users(session)]
    if not entries:
        await message.answer("Пока нет участников.")
        return

    lines = ["🏆 Таблица лидеров"]
    for index, (name, score_value) in enumerate(sorted(entries, key=lambda item: item[1], reverse=True), start=1):
        lines.append(f"{index}. {name} — {score_value} баллов")
    await message.answer("\n".join(lines))


@router.message(Command("balance", "me"))
async def show_balance(message: Message) -> None:
    if message.from_user is None:
        return
    with session_scope() as session:
        user = _get_user(session, message.from_user.id)
        if not user:
            await message.answer("Сначала /start")
            return
        text = _format_balance(user)
    await message.answer(text)


@router.message(Command("history"))
async def history(message: Message) -> None:
    if message.from_user is None:
        return
    with session_scope() as session:
        user = _get_user(session, message.from_user.id)
        if not user:
            await message.answer("Сначала /start")
            return
        rows = (
            session.query(ScoreEvent)
            .filter(ScoreEvent.user_id == user.id)
            .order_by(ScoreEvent.created_at.desc())
            .limit(20)
            .all()
        )
        text = _format_history(rows)
    await message.answer(text)
