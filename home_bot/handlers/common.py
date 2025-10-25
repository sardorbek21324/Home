from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from ..db.repo import get_session, list_users

router = Router()

@router.message(Command("rating"))
async def rating(message: Message):
    with get_session() as s:
        users = list_users(s)
        users_sorted = sorted(users, key=lambda u: u.monthly_points, reverse=True)
        lines = []
        for i, u in enumerate(users_sorted, start=1):
            nm = u.nickname or u.name
            lines.append(f"{i}. {nm} — {u.monthly_points} баллов")
        if not lines:
            lines = ["Пока нет данных."]
        await message.answer("🏆 Таблица лидеров:\n" + "\n".join(lines))
