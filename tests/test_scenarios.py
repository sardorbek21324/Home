import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _ensure_configured() -> None:
    if not BOT_TOKEN or not GROUP_CHAT_ID:
        raise RuntimeError("TELEGRAM_TOKEN и GROUP_CHAT_ID должны быть заданы")


async def send_message(chat_id: str | int, text: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text}
        )
        print(f"Sent '{text}': {response.status_code}")
        return response.json()


async def get_updates(offset: int | None = None) -> dict:
    params = {"timeout": 100}
    if offset:
        params["offset"] = offset
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(f"{API_URL}/getUpdates", params=params)
        return response.json()


async def main() -> None:
    _ensure_configured()

    print("--- ЗАПУСК ТЕСТОВОГО СЦЕНАРИЯ ---")
    print("ВНИМАНИЕ: запустите бота перед выполнением скрипта.")

    await send_message(GROUP_CHAT_ID, "/start")
    print("Ожидается ответ на /start...")

    await send_message(GROUP_CHAT_ID, "/статистика")
    print("Ожидается личная статистика...")

    print("\n--- Сценарий 'Успешная готовка' ---")
    await send_message(GROUP_CHAT_ID, "/force_task Приготовить завтрак")
    print("Ожидается сообщение с предложением задачи...")

    print("\n--- Тестовый сценарий завершен ---")
    print("Сложные сценарии требуют отслеживания обновлений и нажатий кнопок вручную.")


if __name__ == "__main__":
    asyncio.run(main())
