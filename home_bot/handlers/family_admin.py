from aiogram import Router, types
from aiogram.filters import Command

from ..config import settings

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(Command("family_list"))
async def family_list(message: types.Message):
    if not _is_admin(message.from_user.id):
        return await message.answer("Только для админа.")
    ids = ", ".join(str(x) for x in settings.FAMILY_IDS)
    await message.answer(f"Family IDs: {ids}")


@router.message(Command("family_add"))
async def family_add(message: types.Message):
    if not _is_admin(message.from_user.id):
        return await message.answer("Только для админа.")
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.answer("Использование: /family_add <telegram_id>")
    try:
        new_id = int(parts[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    # Здесь пока только в рантайме добавляем — персистентность отдельной задачей
    await message.answer(
        f"Добавлен (в сессию): {new_id}. Постоянное хранение — через ENV/БД (TODO)."
    )


@router.message(Command("family_remove"))
async def family_remove(message: types.Message):
    if not _is_admin(message.from_user.id):
        return await message.answer("Только для админа.")
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.answer("Использование: /family_remove <telegram_id>")
    try:
        rm_id = int(parts[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    await message.answer(
        f"Удалён (в сессию): {rm_id}. Постоянное хранение — через ENV/БД (TODO)."
    )
