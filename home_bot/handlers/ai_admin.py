"""Admin commands for managing the AI reward controller."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import settings
from ..db.repo import session_scope
from ..services.ai_controller import AIController

router = Router()


def _require_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in settings.ADMIN_IDS)


@router.message(Command("ai_stats"))
async def ai_stats(message: Message) -> None:
    if not _require_admin(message):
        await message.answer("Команда доступна только администраторам.")
        return

    controller = AIController()
    with session_scope() as session:
        stats = controller.get_user_stats(session)
        config = controller.get_config(session)
    if not stats:
        await message.answer(
            (
                "Данных пока нет. Никто не выполнял задания.\n"
                f"Текущие параметры: penalty={config.penalty_step:.2f}, "
                f"bonus={config.bonus_step:.2f}, range={config.min_coefficient:.2f}-{config.max_coefficient:.2f}."
            )
        )
        return

    lines = [
        "⚙️ AI статистика:",
        f"Параметры: penalty={config.penalty_step:.2f}, bonus={config.bonus_step:.2f}, range={config.min_coefficient:.2f}-{config.max_coefficient:.2f}",
        "Пользователи:",
    ]
    for item in stats:
        lines.append(
            f"• {item.name}: coef={item.coefficient:.2f}, взято={item.taken}, завершено={item.completed}, пропущено={item.skipped}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("ai_config"))
async def ai_config(message: Message) -> None:
    if not _require_admin(message):
        await message.answer("Команда доступна только администраторам.")
        return

    parts = message.text.split()[1:]
    controller = AIController()
    updates: dict[str, float] = {}
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        try:
            updates[key] = float(value)
        except ValueError:
            await message.answer(f"Не удалось распарсить значение для {key!r}.")
            return

    with session_scope() as session:
        if updates:
            controller.update_config(
                session,
                penalty_step=updates.get("penalty", updates.get("penalty_step")),
                bonus_step=updates.get("bonus", updates.get("bonus_step")),
                min_coefficient=updates.get("min", updates.get("min_coeff")),
                max_coefficient=updates.get("max", updates.get("max_coeff")),
                default_coefficient=updates.get("default"),
            )
        config = controller.get_config(session)
    await message.answer(
        (
            "Текущие параметры AI:\n"
            f"• penalty_step={config.penalty_step:.2f}\n"
            f"• bonus_step={config.bonus_step:.2f}\n"
            f"• min_coefficient={config.min_coefficient:.2f}\n"
            f"• max_coefficient={config.max_coefficient:.2f}\n"
            f"• default_coefficient={config.default_coefficient:.2f}"
        )
    )
