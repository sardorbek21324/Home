from aiogram import Router, types
from aiogram.filters import Command

from ..config import settings
from ..services.family import add_family_member, get_family_ids, remove_family_member
from .tasks import build_tasks_overview
from ..utils.telegram import answer_safe

router = Router()


def _is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in settings.ADMIN_IDS)


@router.message(Command("family_list"))
async def family_list(message: types.Message) -> None:
    if not _is_admin(message.from_user and message.from_user.id):
        await answer_safe(message, "Команда только для администраторов.")
        return
    ids = get_family_ids()
    if ids:
        body = "\n".join(f"• <code>{value}</code>" for value in ids)
        text = "👨‍👩‍👧‍👦 Текущий состав семьи:\n" + body
    else:
        text = "Список семьи пуст."
    overview = build_tasks_overview(active_only=True)
    await answer_safe(message, f"{text}\n\n{overview}")


@router.message(Command("family_add"))
async def family_add(message: types.Message) -> None:
    if not _is_admin(message.from_user and message.from_user.id):
        await answer_safe(message, "Команда только для администраторов.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await answer_safe(message, "Использование: /family_add <telegram_id>")
        return
    try:
        new_id = int(parts[1])
    except ValueError:
        await answer_safe(message, "ID должен быть числом.")
        return
    if not add_family_member(new_id):
        await answer_safe(message, "Этот ID уже есть в списке семьи.")
        return
    ids = get_family_ids()
    body = "\n".join(f"• <code>{value}</code>" for value in ids)
    await answer_safe(message, "Готово! Обновлённый список:\n" + body)


@router.message(Command("family_remove"))
async def family_remove(message: types.Message) -> None:
    if not _is_admin(message.from_user and message.from_user.id):
        await answer_safe(message, "Команда только для администраторов.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await answer_safe(message, "Использование: /family_remove <telegram_id>")
        return
    try:
        target = int(parts[1])
    except ValueError:
        await answer_safe(message, "ID должен быть числом.")
        return
    if not remove_family_member(target):
        await answer_safe(message, "Такого ID нет в списке семьи.")
        return
    ids = get_family_ids()
    if ids:
        body = "\n".join(f"• <code>{value}</code>" for value in ids)
        await answer_safe(message, "Удалено. Текущий список:\n" + body)
    else:
        await answer_safe(message, "Удалено. Список семьи пуст.")
