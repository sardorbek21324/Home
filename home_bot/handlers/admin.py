from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from ..config import settings
from ..db.repo import get_session
from ..db.models import User

router = Router()

@router.message(Command("end_month"))
async def end_month(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("Только админ.")
        return
    with get_session() as s:
        users = s.query(User).all()
        if not users:
            await message.answer("Нет пользователей.")
            return
        winner = max(users, key=lambda u: u.monthly_points)
        lines = [f"{(u.nickname or u.name)} — {u.monthly_points}" for u in sorted(users, key=lambda x: x.monthly_points, reverse=True)]
        for u in users:
            u.monthly_points = 0
        s.commit()
    await message.answer("🏁 Итоги месяца:\n" + "\n".join(lines) + f"\n\n🥇 Победитель: {winner.nickname or winner.name}")
