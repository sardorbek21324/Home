from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from ..db.repo import get_session, upsert_user, list_users, get_user_by_tid, init_db, get_or_create_tasks_from_seed
from ..db.models import Role
from ..config import settings
import json
from pathlib import Path

router = Router()

@router.message(CommandStart())
async def start(message: Message):
    init_db()
    seed_path = Path(__file__).resolve().parents[2] / "data" / "seed_tasks.json"
    with open(seed_path, "r", encoding="utf-8") as f:
        seed = json.load(f)
    with get_session() as s:
        get_or_create_tasks_from_seed(s, seed)
        role = Role.admin if message.from_user.id in settings.ADMIN_IDS else Role.member
        user = upsert_user(s, telegram_id=message.from_user.id, name=message.from_user.full_name, nickname=message.from_user.username, role=role)
    await message.answer(
        "👋 Привет! Я бот для домашних задач.\n"
        "Команды:\n"
        "• /rating — рейтинг\n"
        "• /history — моя история\n"
        "• /announce — (админ) выслать тестовую задачу сейчас\n"
        "• /end_month — (админ) финал месяца"
    )

@router.message(Command("rating"))
async def rating(message: Message):
    with get_session() as s:
        users = list_users(s)
        users_sorted = sorted(users, key=lambda u: u.monthly_points, reverse=True)
        lines = []
        for i, u in enumerate(users_sorted, start=1):
            nm = u.nickname or u.name
            lines.append(f"{i}. {nm} — {u.monthly_points} баллов")
        if not lines:
            lines = ["Пока нет данных."]
        await message.answer("🏆 Таблица лидеров:\n" + "\n".join(lines))
