from aiogram import Router, types
from aiogram.filters import Command

from ..config import settings
from ..services.family import add_family_member, get_family_ids, remove_family_member

router = Router()


def _is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in settings.ADMIN_IDS)


@router.message(Command("family_list"))
async def family_list(message: types.Message) -> None:
    if not _is_admin(message.from_user and message.from_user.id):
        await message.answer("Команда только для администраторов.")
        return
    ids = get_family_ids()
    if ids:
        body = "\n".join(f"• <code>{value}</code>" for value in ids)
        text = "👨‍👩‍👧‍👦 Текущий состав семьи:\n" + body
    else:
        text = "Список семьи пуст."
    await message.answer(text)


@router.message(Command("family_add"))
async def family_add(message: types.Message) -> None:
    if not _is_admin(message.from_user and message.from_user.id):
        await message.answer("Команда только для администраторов.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /family_add <telegram_id>")
        return
    try:
        new_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    if not add_family_member(new_id):
        await message.answer("Этот ID уже есть в списке семьи.")
        return
    ids = get_family_ids()
    body = "\n".join(f"• <code>{value}</code>" for value in ids)
    await message.answer("Готово! Обновлённый список:\n" + body)


@router.message(Command("family_remove"))
async def family_remove(message: types.Message) -> None:
    if not _is_admin(message.from_user and message.from_user.id):
        await message.answer("Команда только для администраторов.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /family_remove <telegram_id>")
        return
    try:
        target = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    if not remove_family_member(target):
        await message.answer("Такого ID нет в списке семьи.")
        return
    ids = get_family_ids()
    if ids:
        body = "\n".join(f"• <code>{value}</code>" for value in ids)
        await message.answer("Удалено. Текущий список:\n" + body)
    else:
        await message.answer("Удалено. Список семьи пуст.")
