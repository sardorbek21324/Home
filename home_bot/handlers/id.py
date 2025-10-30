from aiogram import Router, types
from aiogram.filters import Command

from ..utils.telegram import answer_safe
from ..utils.text import escape_html

router = Router()


@router.message(Command("myid", "getid", "id"))
async def myid(message: types.Message):
    uid = message.from_user.id
    name = escape_html((message.from_user.full_name or "").strip())
    await answer_safe(message, f"Твой Telegram ID: <code>{uid}</code>\n{name}")
