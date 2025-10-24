import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from .config import settings
from .utils.logging import setup_logging
from .db.repo import init_db
from .handlers import common, tasks, score, admin, profile
from .services.scheduler import BotScheduler

bot = None
dp = None
scheduler = None

async def main():
    setup_logging()
    logging.getLogger(__name__).info("Starting bot...")
    init_db()

    global bot, dp, scheduler
    bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.include_router(common.router)
    dp.include_router(tasks.router)
    dp.include_router(score.router)
    dp.include_router(admin.router)
    dp.include_router(profile.router)

    scheduler = BotScheduler(bot)
    scheduler.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
