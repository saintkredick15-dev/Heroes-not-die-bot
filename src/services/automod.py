"""
automod.py
Система автоматичної модерації (включаючи кастомні теги-фільтри).
Використовує in-memory кеш, щоб не перевантажувати базу даних запитами.
"""
import re
import discord
from discord.ext import commands
from modules.db import get_database

db = get_database()

# In-memory кеш для правил { guild_id: [rule_dict, ...] }
_RULES_CACHE: dict[int, list[dict]] = {}

def normalize_string(text: str) -> str:
    """Нормалізує рядок (переводить кирилицю в латиницю, прибирає зайві символи)."""
    if not text:
        return ""
    text = text.upper()
    replacements = {
        "А": "A", "В": "B", "Е": "E", "З": "3", "І": "I",
        "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
        "С": "C", "Т": "T", "У": "Y", "Х": "X"
    }
    for cyr, lat in replacements.items():
        text = text.replace(cyr, lat)
    # Залишаємо тільки букви і цифри для порівняння
    return re.sub(r'[^A-Z0-9]', '', text)

async def load_automod_cache(bot: commands.Bot):
    """Викликати при старті бота. Завантажує всі правила в оперативну пам'ять."""
    global _RULES_CACHE
    _RULES_CACHE.clear()
    cursor = db.guild_settings.find({"automod_rules": {"$exists": True}})
    async for guild_data in cursor:
        guild_id = guild_data["_id"]
        _RULES_CACHE[guild_id] = guild_data.get("automod_rules", [])
    print(f"[Automod] Cache loaded for {len(_RULES_CACHE)} guilds.")

async def reload_guild_automod_cache(guild_id: int):
    """Оновлює кеш для одного сервера (викликається після /automod)."""
    settings = await db.guild_settings.find_one({"_id": guild_id})
    if settings and "automod_rules" in settings:
        _RULES_CACHE[guild_id] = settings["automod_rules"]
    else:
        _RULES_CACHE.pop(guild_id, None)

def check_member_tags(guild_id: int, member: discord.Member) -> dict | None:
    """Синхронно перевіряє (через кеш) чи порушив учасник правила Автомода.
    Повертає словник порушеного правила або None.
    """
    rules = _RULES_CACHE.get(guild_id, [])
    if not rules:
        return None

    # Перевіряємо Нікнейм, Global Name та Activities
    text_to_check = f"{member.display_name} {member.global_name or ''} "
    for activity in member.activities:
        if hasattr(activity, 'name') and activity.name:
            text_to_check += f"{activity.name} "
        if hasattr(activity, 'state') and activity.state:
            text_to_check += f"{activity.state} "
        if hasattr(activity, 'details') and activity.details:
            text_to_check += f"{activity.details} "

    normalized_text = normalize_string(text_to_check)

    for rule in rules:
        normalized_rule = normalize_string(rule["trigger"])
        if normalized_rule and normalized_rule in normalized_text:
            return rule

    return None
