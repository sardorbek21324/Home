"""Inline menu with quick actions."""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..config import settings
from . import score, tasks

router = Router()


def build_menu_keyboard(user: types.User | None) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📋 Задания", callback_data="menu:tasks")],
        [InlineKeyboardButton(text="🏆 Баланс", callback_data="menu:score")],
        [InlineKeyboardButton(text="📜 История", callback_data="menu:history")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help")],
    ]
    if user and user.id in settings.ADMIN_IDS:
        buttons.append([InlineKeyboardButton(text="⚙️ AI Настройки", callback_data="menu:ai")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def render_menu_view(action: str, user: types.User | None) -> str:
    if action == "tasks":
        return tasks.build_tasks_overview()
    if action == "score" and user:
        return score.build_balance_text(user.id)
    if action == "history" and user:
        return score.build_history_text(user.id)
    if action == "help":
        cmds = [
            "<b>Основные</b>",
            "/tasks — список задач",
            "/me — мои баллы",
            "/history — история",
            "/myid — мой Telegram ID",
            "/selftest — диагностика",
            "/ai_test — проверка AI-контроллера",
            "<b>Админы</b>",
            "/family_list /family_add /family_remove",
            "/regen_today — пересоздать задачи",
            "/debug_jobs — статус планировщика",
            "/ai_stats — коэффициенты вознаграждений",
            "/ai_config — управление параметрами AI",
        ]
        return "⚙️ Помощь:\n" + "\n".join(cmds)
    if action == "ai" and user and user.id in settings.ADMIN_IDS:
        return (
            "⚙️ Настройки AI:\n"
            "• /ai_stats — показатели пользователей и коэффициенты\n"
            "• /ai_config penalty=0.1 bonus=0.05 — изменить параметры"
        )
    greeting = [
        "👋 Привет! Я помогу распределять домашние дела.",
        "Выбирай пункт ниже, чтобы посмотреть задачи, баланс и историю.",
    ]
    if user and user.id in settings.ADMIN_IDS:
        greeting.append("У тебя есть права администратора — доступны команды для управления семьёй и AI.")
    return "\n\n".join(greeting)


@router.message(Command("menu"))
async def show_menu(message: types.Message) -> None:
    await message.answer(
        await render_menu_view("home", message.from_user),
        reply_markup=build_menu_keyboard(message.from_user),
    )


@router.callback_query(F.data.startswith("menu:"))
async def handle_menu_callback(callback: types.CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    _, _, action = callback.data.partition(":")
    text = await render_menu_view(action or "home", callback.from_user)
    await callback.message.edit_text(
        text,
        reply_markup=build_menu_keyboard(callback.from_user),
    )
    await callback.answer()
