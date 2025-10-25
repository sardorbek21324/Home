from aiogram import Router, types
from aiogram.filters import Command

from ..services.ai_advisor import AIAdvisor

router = Router()


@router.message(Command("ai_test"))
async def ai_test(message: types.Message):
    advisor = AIAdvisor()
    status = await advisor.healthcheck()
    await message.answer(f"AI health: {status}")
