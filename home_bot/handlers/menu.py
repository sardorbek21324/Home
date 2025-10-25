"""Inline menu with quick actions."""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import settings
from ..services.ai_advisor import AIAdvisor
from . import score, tasks

router = Router()

_MENU_BUTTONS: list[tuple[str, str]] = [
    ("📋 Задачи сегодня", "menu:tasks"),
    ("🏆 Баллы", "menu:score"),
    ("🧾 История", "menu:history"),
    ("🧠 Совет дня (ИИ)", "menu:advice"),
    ("⚙️ Помощь", "menu:help"),
]


def build_menu_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, data in _MENU_BUTTONS:
        builder.button(text=text, callback_data=data)
    builder.adjust(1)
    return builder.as_markup()


async def render_menu_view(action: str, user: types.User | None) -> str:
    if action == "tasks":
        return tasks.build_tasks_overview()
    if action == "score" and user:
        return score.build_balance_text(user.id)
    if action == "history" and user:
        return score.build_history_text(user.id)
    if action == "advice":
        overview = tasks.build_tasks_overview()
        advisor = AIAdvisor()
        advice = await advisor.suggest_daily_focus(overview)
        return f"<b>{advice.title}</b>\n{advice.text}"
    if action == "help":
        cmds = [
            "<b>Основные</b>",
            "/tasks — список задач",
            "/me — мои баллы",
            "/history — история",
            "/myid — мой Telegram ID",
            "/selftest — диагностика",
            "<b>Админы</b>",
            "/family_list /family_add /family_remove",
            "/regen_today — пересоздать задачи",
            "/debug_jobs — статус планировщика",
        ]
        return "⚙️ Помощь:\n" + "\n".join(cmds)
    greeting = [
        "👋 Привет! Я помогу распределять домашние дела.",
        "Выбирай пункт ниже, чтобы посмотреть задачи, баланс или подсказку ИИ.",
    ]
    if user and user.id in settings.ADMIN_IDS:
        greeting.append("У тебя есть права администратора — в меню доступны команды для управления семьёй.")
    return "\n\n".join(greeting)


@router.message(Command("menu"))
async def show_menu(message: types.Message) -> None:
    await message.answer(await render_menu_view("home", message.from_user), reply_markup=build_menu_keyboard())


@router.callback_query(F.data.startswith("menu:"))
async def handle_menu_callback(callback: types.CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    _, _, action = callback.data.partition(":")
    text = await render_menu_view(action or "home", callback.from_user)
    await callback.message.edit_text(text, reply_markup=build_menu_keyboard())
    await callback.answer()
