from aiogram import Router, types
from aiogram.filters import Command

from ..services.ai_controller import AIController

router = Router()


@router.message(Command("ai_test"))
async def ai_test(message: types.Message):
    controller = AIController()
    status = controller.healthcheck()
    await message.answer(f"AI controller: {status}")
