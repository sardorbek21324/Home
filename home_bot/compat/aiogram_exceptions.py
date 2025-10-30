# home_bot/compat/aiogram_exceptions.py
try:
    # Aiogram v3
    from aiogram.exceptions import MessageNotModified, TelegramBadRequest
except Exception:
    # Aiogram v2
    from aiogram.utils.exceptions import MessageNotModified, BadRequest as TelegramBadRequest

__all__ = ["MessageNotModified", "TelegramBadRequest"]
