from aiogram import Router, types

from ..services.ai_advisor import AIAdvisor

router = Router()


@router.message(commands={"ai_test"})
async def ai_test(message: types.Message) -> None:
    advisor = AIAdvisor()
    status = await advisor.healthcheck()
    await message.answer(f"AI health: {status}")
