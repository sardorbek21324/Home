from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from ..db.repo import get_session, get_user_by_tid
from ..db.models import Status

router = Router()

@router.message(Command("status"))
async def set_status(message: Message):
    with get_session() as s:
        u = get_user_by_tid(s, message.from_user.id)
        if not u:
            await message.answer("Сначала /start")
            return
        u.status = Status.day_off if u.status == Status.available else Status.available
        s.commit()
        await message.answer(f"Статус изменен на: {u.status}")
