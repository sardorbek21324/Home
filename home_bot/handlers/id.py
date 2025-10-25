from aiogram import Router, types

router = Router()


@router.message(commands={"myid", "getid", "id"})
async def myid(message: types.Message) -> None:
    user = message.from_user
    if not user:
        await message.answer("Не удалось определить ваш Telegram ID.")
        return
    uid = user.id
    name = (user.full_name or "").strip()
    await message.answer(f"Твой Telegram ID: <code>{uid}</code>\n{name}")
