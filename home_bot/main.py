"""Telegram bot entry point used by hosting platforms."""
from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .config import BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Привет! Отправь /ping, чтобы проверить, что бот живой."
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to /ping to confirm the bot is alive."""
    await update.message.reply_text("Бот работает! ✅")


def main() -> None:
    """Run the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))

    logger.info("Bot is starting. Waiting for commands…")
    application.run_polling()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
