from aiogram import Router, types

from ..config import settings

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(commands={"family_list"})
async def family_list(message: types.Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для админа.")
        return
    ids = ", ".join(str(x) for x in settings.FAMILY_IDS) or "—"
    await message.answer(f"Family IDs: {ids}")


@router.message(commands={"family_add"})
async def family_add(message: types.Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для админа.")
        return
    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        await message.answer("Использование: /family_add <telegram_id>")
        return
    try:
        new_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    ids = set(settings.FAMILY_IDS)
    ids.add(new_id)
    await message.answer(
        f"Добавлен (в сессию): {new_id}. Персистентность через ENV/БД (TODO)."
    )


@router.message(commands={"family_remove"})
async def family_remove(message: types.Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для админа.")
        return
    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        await message.answer("Использование: /family_remove <telegram_id>")
        return
    try:
        rm_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    ids = set(settings.FAMILY_IDS)
    if rm_id in ids:
        ids.remove(rm_id)
        await message.answer(
            f"Удалён (в сессию): {rm_id}. Персистентность через ENV/БД (TODO)."
        )
    else:
        await message.answer("Такого ID нет в текущем списке.")
