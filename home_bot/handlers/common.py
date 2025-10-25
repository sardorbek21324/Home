"""Miscellaneous commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


router = Router()


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/menu — открыть меню\n"
        "/rating — таблица лидеров\n"
        "/me — мой баланс\n"
        "/history — история операций\n"
        "Админы: /announce, /add_task, /end_month"
    )
