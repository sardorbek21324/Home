from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from ..db.repo import get_session
from ..db.models import History, User

router = Router()

@router.message(Command("history"))
async def my_history(message: Message):
    with get_session() as s:
        user = s.query(User).filter_by(telegram_id=message.from_user.id).one_or_none()
        if not user:
            await message.answer("Сначала /start")
            return
        rows = s.query(History).filter(History.user_id == user.id).order_by(History.created_at.desc()).limit(20).all()
        if not rows:
            await message.answer("История пуста.")
            return
        text = "📜 Последние операции:\n"
        for h in rows:
            sign = "➕" if h.delta > 0 else "➖"
            text += f"{sign}{abs(h.delta)} — {h.reason} ({h.created_at:%Y-%m-%d %H:%M})\n"
        await message.answer(text)
