"""Start command handler."""

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import BotCommand

from ..config import settings
from ..db.repo import ensure_user, session_scope
from .menu import main_menu


router = Router()


@router.message(Command("start"))
async def start_cmd(message: types.Message) -> None:
    if message.from_user is None:
        return

    with session_scope() as session:
        ensure_user(session, message.from_user.id, message.from_user.full_name, message.from_user.username)

    is_admin = message.from_user.id in settings.ADMIN_IDS
    await message.bot.set_my_commands(
        [
            BotCommand(command="menu", description="Открыть меню"),
            BotCommand(command="rating", description="Таблица лидеров"),
            BotCommand(command="me", description="Мой баланс"),
            BotCommand(command="history", description="История"),
            BotCommand(command="help", description="Помощь"),
        ]
    )
    await message.answer(
        "👋 Привет! Я помогу вести домашние дела.\n\n"
        "Что дальше:\n"
        "• Нажми /menu, чтобы открыть клавиатуру.\n"
        "• /tasks — посмотреть доступные задачи.\n"
        "• /me и /history — твой счёт и события.",
        reply_markup=main_menu(is_admin),
    )
