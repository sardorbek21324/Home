from aiogram import Router, types
from aiogram.filters import Command

from ..db.repo import ensure_user, session_scope
from .menu import build_menu_keyboard, render_menu_view

router = Router()


@router.message(Command("start"))
async def start_cmd(message: types.Message) -> None:
    if message.from_user is None:
        return

    with session_scope() as session:
        ensure_user(
            session,
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username,
        )

    text = await render_menu_view("home", message.from_user)
    extra = (
        "\n\n• Жми кнопки ниже, чтобы посмотреть задачи или баланс."
        "\n• /tasks — прислать список текстом."
        "\n• /me и /history — быстрый доступ к очкам."
    )
    await message.answer(text + extra, reply_markup=build_menu_keyboard())
