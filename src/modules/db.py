import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Завантажуємо .env відносно кореня проєкту (незалежно від CWD)
load_dotenv(Path(__file__).parents[2] / ".env")

# --- Singleton ---
_client: AsyncIOMotorClient | None = None


def get_database():
    """
    Повертає об'єкт бази даних.
    Singleton: AsyncIOMotorClient створюється один раз на весь процес,
    що запобігає витоку ресурсів і повторному підключенню.
    """
    global _client
    if _client is None:
        mongo_url = os.getenv("MONGO_DB")
        if not mongo_url:
            raise ValueError(
                "MONGO_DB не знайдено у .env файлі. "
                "Переконайтесь що .env існує та містить MONGO_DB=<url>"
            )
        _client = AsyncIOMotorClient(mongo_url)
    return _client.discord_bot