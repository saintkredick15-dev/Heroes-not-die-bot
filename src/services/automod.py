"""
automod.py
Система автоматичної модерації (включаючи кастомні теги-фільтри та модулі антиспаму/антилінків).
Використовує in-memory кеш, щоб не перевантажувати базу даних запитами.
"""
import re
import discord
from discord.ext import commands
from modules.db import get_database

db = get_database()

# In-memory кеш для правил { guild_id: dict_of_settings }
_RULES_CACHE: dict[int, dict] = {}

def normalize_string(text: str) -> str:
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
    return re.sub(r'[^A-Z0-9]', '', text)


async def load_automod_cache(bot: commands.Bot):
    global _RULES_CACHE
    _RULES_CACHE.clear()
    cursor = db.guild_settings.find({})
    async for gd in cursor:
        guild_id = gd["_id"]
        _RULES_CACHE[guild_id] = {
            "automod_rules": gd.get("automod_rules", []),
            "am_antispam": gd.get("am_antispam", False),
            "am_antiinvite": gd.get("am_antiinvite", False),
            "am_antilink": gd.get("am_antilink", False),
            "am_caps": gd.get("am_caps", False),
            "am_mentions": gd.get("am_mentions", False),
            "am_whitelist_channels": gd.get("am_whitelist_channels", []),
            "am_whitelist_roles": gd.get("am_whitelist_roles", []),
        }
    print(f"[Automod] Cache loaded for {len(_RULES_CACHE)} guilds.")


async def reload_guild_automod_cache(guild_id: int):
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    _RULES_CACHE[guild_id] = {
        "automod_rules": settings.get("automod_rules", []),
        "am_antispam": settings.get("am_antispam", False),
        "am_antiinvite": settings.get("am_antiinvite", False),
        "am_antilink": settings.get("am_antilink", False),
        "am_caps": settings.get("am_caps", False),
        "am_mentions": settings.get("am_mentions", False),
        "am_whitelist_channels": settings.get("am_whitelist_channels", []),
        "am_whitelist_roles": settings.get("am_whitelist_roles", []),
    }


def get_automod_config(guild_id: int) -> dict:
    return _RULES_CACHE.get(guild_id, {})


def check_member_tags(guild_id: int, member: discord.Member) -> dict | None:
    config = get_automod_config(guild_id)
    rules = config.get("automod_rules", [])
    if not rules:
        return None

    text_to_check = f"{member.display_name} {member.global_name or ''} "
    for activity in member.activities:
        if hasattr(activity, 'name') and activity.name: text_to_check += f"{activity.name} "
        if hasattr(activity, 'state') and activity.state: text_to_check += f"{activity.state} "
        if hasattr(activity, 'details') and activity.details: text_to_check += f"{activity.details} "

    normalized_text = normalize_string(text_to_check)

    for rule in rules:
        normalized_rule = normalize_string(rule["trigger"])
        if normalized_rule and normalized_rule in normalized_text:
            return rule

    return None
