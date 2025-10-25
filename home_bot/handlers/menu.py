"""Reply keyboard with quick actions."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from ..config import settings
from . import score, tasks


router = Router()


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📊 Баланс"), KeyboardButton(text="📅 История")],
        [KeyboardButton(text="🧹 Задачи")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Админ")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


@router.message(Command("menu"))
async def show_menu(message: Message) -> None:
    is_admin = message.from_user and message.from_user.id in settings.ADMIN_IDS
    await message.answer("Меню действий доступно ниже.", reply_markup=main_menu(is_admin))


@router.message(lambda m: m.text == "📊 Баланс")
async def balance_from_menu(message: Message) -> None:
    await score.show_balance(message)


@router.message(lambda m: m.text == "📅 История")
async def history_from_menu(message: Message) -> None:
    await score.history(message)


@router.message(lambda m: m.text == "🧹 Задачи")
async def tasks_from_menu(message: Message) -> None:
    await tasks.tasks_list(message)


@router.message(lambda m: m.text == "🛠 Админ")
async def admin_from_menu(message: Message) -> None:
    if message.from_user and message.from_user.id in settings.ADMIN_IDS:
        await message.bot.send_message(message.chat.id, "Админ-команды: /announce, /add_task, /end_month, /disputes")
    else:
        await message.answer("Недостаточно прав.")
