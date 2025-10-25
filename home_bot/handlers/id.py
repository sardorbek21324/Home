from aiogram import Router, types
from aiogram.filters import Command

router = Router()


@router.message(Command("myid", "getid", "id"))
async def myid(message: types.Message):
    uid = message.from_user.id
    name = (message.from_user.full_name or "").strip()
    await message.answer(f"Твой Telegram ID: <code>{uid}</code>\n{name}")
