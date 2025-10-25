"""Handlers for rating and personal stats."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..db.models import ScoreEvent, User
from ..db.repo import list_users, session_scope


router = Router()


@router.message(Command("rating"))
async def show_rating(message: Message) -> None:
    with session_scope() as session:
        entries = [(user.username or user.name, user.score) for user in list_users(session)]
    if not entries:
        await message.answer("Пока нет участников.")
        return

    lines = ["🏆 Таблица лидеров"]
    for index, (name, score_value) in enumerate(sorted(entries, key=lambda item: item[1], reverse=True), start=1):
        lines.append(f"{index}. {name} — {score_value} баллов")
    await message.answer("\n".join(lines))


@router.message(Command("me"))
async def me(message: Message) -> None:
    if message.from_user is None:
        return
    with session_scope() as session:
        user = session.query(User).filter(User.tg_id == message.from_user.id).one_or_none()
        if not user:
            await message.answer("Сначала /start")
            return
        score_value = user.score
    await message.answer(f"Твой текущий баланс: {score_value} баллов.")


@router.message(Command("history"))
async def history(message: Message) -> None:
    if message.from_user is None:
        return
    with session_scope() as session:
        user = session.query(User).filter(User.tg_id == message.from_user.id).one_or_none()
        if not user:
            await message.answer("Сначала /start")
            return
        rows = [
            (event.created_at, event.delta, event.reason)
            for event in session.query(ScoreEvent)
            .filter(ScoreEvent.user_id == user.id)
            .order_by(ScoreEvent.created_at.desc())
            .limit(20)
            .all()
        ]
    if not rows:
        await message.answer("История пуста.")
        return

    lines = ["📅 Последние события"]
    for created_at, delta, reason in rows:
        sign = "➕" if delta >= 0 else "➖"
        lines.append(f"{created_at:%d.%m %H:%M} — {sign}{abs(delta)} за {reason}")
    await message.answer("\n".join(lines))
