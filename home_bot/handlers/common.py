"""Miscellaneous commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


router = Router()


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    text = (
        "Команды:\n"
        "/menu — открыть меню\n"
        "/tasks — задачи сегодня\n"
        "/rating — таблица лидеров\n"
        "/me — мой баланс\n"
        "/history — история операций\n"
        "/myid — узнать свой Telegram ID\n"
        "/selftest — самодиагностика\n"
        "/ai_test — проверка OpenAI\n"
        "Админы: /family_list, /family_add, /family_remove, /regen_today, /debug_jobs"
    )
    await message.answer(text)
