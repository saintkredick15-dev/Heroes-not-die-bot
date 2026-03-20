import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

_client: AsyncIOMotorClient | None = None

def get_database():
    
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

from utils.cache import guild_settings_cache, user_data_cache

async def get_guild_settings(db, guild_id: int) -> dict:
    # Спочатку чекаємо кеш, якщо пусто - ліземо в MongoDB
    key = str(guild_id)
    cached_data = await guild_settings_cache.get(key)
    if cached_data is not None:
        return cached_data
        
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    
    await guild_settings_cache.set(key, settings)
    return settings

async def invalidate_guild_settings(guild_id: int):
    
    await guild_settings_cache.invalidate(str(guild_id))

async def get_user_data(db, guild_id: int, user_id: int) -> dict:
    # Тягнемо юзера з кешу, щоб не спамити базу
    key = f"{guild_id}_{user_id}"
    cached_data = await user_data_cache.get(key)
    if cached_data is not None:
        return cached_data
        
    data = await db.users.find_one({"guild_id": guild_id, "user_id": user_id}) or {}
    await user_data_cache.set(key, data)
    return data

async def invalidate_user_data(guild_id: int, user_id: int):
    
    await user_data_cache.invalidate(f"{guild_id}_{user_id}")