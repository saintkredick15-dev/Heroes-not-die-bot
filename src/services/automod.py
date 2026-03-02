"""
automod.py
Система автоматичної модерації — кеш конфігурації та утиліти.
Зберігає ВСІ налаштування модулів в in-memory кеші.
"""
import re
import discord
from discord.ext import commands
from modules.db import get_database

db = get_database()

_RULES_CACHE: dict[int, dict] = {}

# Всі ключі модулів, які треба кешувати
_MODULE_KEYS = [
    # toggles
    "am_antispam", "am_antiinvite", "am_antilink", "am_caps", "am_mentions",
    # antispam
    "am_antispam_count", "am_antispam_interval", "am_antispam_action", "am_antispam_mute_dur",
    "am_antispam_duplicates",
    # antiinvite
    "am_antiinvite_action", "am_antiinvite_mute_dur", "am_antiinvite_allowed_servers",
    # antilink
    "am_antilink_action", "am_antilink_mute_dur", "am_antilink_allowed_domains",
    # caps
    "am_caps_percent", "am_caps_minlen", "am_caps_action", "am_caps_mute_dur",
    # mentions
    "am_mentions_max", "am_mentions_action", "am_mentions_mute_dur",
    # whitelists
    "am_whitelist_channels", "am_whitelist_roles",
    # custom rules
    "automod_rules",
]

# Значення за замовчуванням
_DEFAULTS = {
    "am_antispam_count": 5,
    "am_antispam_interval": 5,
    "am_antispam_action": "warn",
    "am_antispam_mute_dur": "",
    "am_antispam_duplicates": False,
    "am_antiinvite_action": "delete",
    "am_antiinvite_mute_dur": "",
    "am_antiinvite_allowed_servers": [],
    "am_antilink_action": "delete",
    "am_antilink_mute_dur": "",
    "am_antilink_allowed_domains": [],
    "am_caps_percent": 70,
    "am_caps_minlen": 8,
    "am_caps_action": "delete",
    "am_caps_mute_dur": "",
    "am_mentions_max": 5,
    "am_mentions_action": "warn",
    "am_mentions_mute_dur": "",
    "am_whitelist_channels": [],
    "am_whitelist_roles": [],
    "automod_rules": [],
}


def _extract_settings(gd: dict) -> dict:
    """Витягує всі automod налаштування з документа БД."""
    result = {}
    for key in _MODULE_KEYS:
        result[key] = gd.get(key, _DEFAULTS.get(key, False))
    return result


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
        _RULES_CACHE[gd["_id"]] = _extract_settings(gd)
    print(f"[Automod] Cache loaded for {len(_RULES_CACHE)} guilds.")


async def reload_guild_automod_cache(guild_id: int):
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    _RULES_CACHE[guild_id] = _extract_settings(settings)


def get_automod_config(guild_id: int) -> dict:
    return _RULES_CACHE.get(guild_id, {})


def check_member_tags(guild_id: int, member: discord.Member) -> dict | None:
    config = get_automod_config(guild_id)
    rules = config.get("automod_rules", [])
    if not rules:
        return None

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
