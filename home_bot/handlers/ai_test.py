from aiogram import Router, types
from aiogram.filters import Command

from ..services.ai_controller import AIController
from ..utils.telegram import answer_safe

router = Router()


@router.message(Command("ai_test"))
async def ai_test(message: types.Message):
    controller = AIController()
    status = controller.healthcheck()
    await answer_safe(message, f"AI controller: {status}")
