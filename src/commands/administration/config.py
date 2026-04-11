from __future__ import annotations

import io
import json
import re

import discord
from discord import app_commands
from discord.ext import commands

from modules.db import get_database
from services.automod import find_matching_rule, reload_guild_automod_cache

from .automod_setup import MODULES as AUTOMOD_MODULES
from .automod_setup import MODULE_SETTINGS as AUTOMOD_SETTINGS
from .economy_setup_shared import DEFAULT_ECO, get_eco, save_eco
from .logs_setup import LOG_TYPES
from .welcome import get_greetings_settings
from utils.restrictions import normalize_command_restrictions
from utils.ui_contract import add_section, compact_kv, set_surface_footer, surface_embed

db = get_database()
_col = db.guild_settings

E_SETTING = "<:settings:1485606007668342865>"
E_CHECK = "<:check:1485597845883981905>"
E_CROSS = "<:close:1485598320935174317>"
E_BANK = "<:bank_safe:1485637217132216571>"
E_HAMMER = "<:hammer:1485606127696609412>"
E_NOTIF = "<:notification_on:1485609281062572142>"
E_LIST = "<:menuandlist:1485605053246083143>"
E_WARN = "<:warning:1485598476850040843>"
E_HI = "<:notification_on:1485609281062572142>"
EMBED_COLOR = 0x1A1A2E
CONFIG_SCHEMA_VERSION = 1
_URL_RE = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE)
_INVITE_RE = re.compile(r'(?:discord\.gg|discord\.com/invite|discordapp\.com/invite|dsc\.gg|discord\.io|invite\.gg)/([a-zA-Z0-9\-]+)', re.IGNORECASE)
_EMOJI_RE = re.compile(r'<a?:\w+:\d+>|[\U0001F600-\U0001FAFF\U00002600-\U000027BF]+')

MODULE_META = {
    "economy": {"label": "Економіка", "emoji": E_BANK, "command": "/economy_setup"},
    "automod": {"label": "Автомод", "emoji": E_HAMMER, "command": "/automod"},
    "server": {"label": "Сервер", "emoji": E_SETTING, "command": "/settings"},
    "logs": {"label": "Логи", "emoji": E_LIST, "command": "/logs"},
    "warnings": {"label": "Попередження", "emoji": E_WARN, "command": "/warn-setup"},
    "welcome": {"label": "Привітання", "emoji": E_HI, "command": "/welcome"},
}

TRUSTED_DOMAIN_PRESET = [
    "youtube.com",
    "youtu.be",
    "tenor.com",
    "giphy.com",
    "github.com",
    "imgur.com",
]

ECONOMY_PRESETS = {
    "casual": {"msg_earn": [8, 14], "voice_earn": 4, "reaction_earn": 3, "work_min": 80, "work_max": 520, "work_cooldown": 10800, "daily_amount": 300, "daily_streak_bonus": 75, "captcha_enabled": False, "rob_chance": 45, "crime_cooldown": 21600, "gambling_enabled": True, "gambling_max_bet": 15000},
    "balanced": {"msg_earn": [5, 10], "voice_earn": 3, "reaction_earn": 2, "work_min": 50, "work_max": 400, "work_cooldown": 14400, "daily_amount": 200, "daily_streak_bonus": 50, "captcha_enabled": False, "rob_chance": 40, "crime_cooldown": 28800, "gambling_enabled": False, "gambling_max_bet": 10000},
    "grindy": {"msg_earn": [3, 7], "voice_earn": 2, "reaction_earn": 1, "work_min": 45, "work_max": 300, "work_cooldown": 18000, "daily_amount": 150, "daily_streak_bonus": 30, "captcha_enabled": True, "rob_chance": 35, "crime_cooldown": 32400, "gambling_enabled": False, "gambling_max_bet": 5000},
    "community": {"msg_earn": [6, 12], "voice_earn": 4, "reaction_earn": 2, "daily_amount": 250, "daily_streak_bonus": 60, "quests_enabled": True, "quests_daily_count": 4, "quests_weekly_count": 3, "fund_enabled": True, "season_enabled": True},
    "competitive": {"msg_earn": [4, 8], "voice_earn": 2, "reaction_earn": 1, "daily_amount": 175, "daily_streak_bonus": 35, "rob_enabled": True, "rob_chance": 38, "crime_enabled": True, "gambling_enabled": False, "season_enabled": True, "bank_interest_rate": 0.0},
    "creator": {"msg_earn": [7, 13], "voice_earn": 5, "reaction_earn": 3, "daily_amount": 260, "daily_streak_bonus": 65, "work_min": 70, "work_max": 420, "fund_enabled": True, "fund_goal": 2500000, "transfer_tax_percent": 1, "quests_enabled": True, "quests_daily_count": 5, "season_enabled": False},
    "roleplay": {"msg_earn": [4, 9], "voice_earn": 2, "reaction_earn": 1, "daily_amount": 220, "daily_streak_bonus": 40, "work_min": 60, "work_max": 260, "bank_interest_rate": 1.5, "bank_interest_interval": "weekly", "shop_roles": [], "season_enabled": True, "season_duration_days": 45, "auction_anti_snipe_seconds": 45},
}

AUTOMOD_PRESETS = {
    "relaxed": {"am_antispam": True, "am_antispam_count": 7, "am_antispam_interval": 5, "am_antispam_action": "warn", "am_antispam_duplicates": False, "am_antiinvite": True, "am_antiinvite_action": "delete", "am_antilink": True, "am_antilink_action": "warn", "am_antilink_allowed_domains": TRUSTED_DOMAIN_PRESET, "am_caps": False, "am_mentions": True, "am_mentions_max": 6, "am_mentions_action": "warn", "am_emojispam": False, "am_imagespam": False},
    "balanced": {"am_antispam": True, "am_antispam_count": 5, "am_antispam_interval": 5, "am_antispam_action": "warn,delete", "am_antispam_duplicates": True, "am_antiinvite": True, "am_antiinvite_action": "delete", "am_antilink": True, "am_antilink_action": "delete", "am_antilink_allowed_domains": TRUSTED_DOMAIN_PRESET, "am_caps": True, "am_caps_percent": 75, "am_caps_minlen": 8, "am_caps_action": "delete", "am_mentions": True, "am_mentions_max": 5, "am_mentions_action": "warn", "am_emojispam": True, "am_emojispam_max": 12, "am_emojispam_action": "delete", "am_imagespam": True, "am_imagespam_count": 4, "am_imagespam_interval": 8, "am_imagespam_action": "warn"},
    "strict": {"am_antispam": True, "am_antispam_count": 4, "am_antispam_interval": 4, "am_antispam_action": "delete,mute", "am_antispam_mute_dur": "30m", "am_antispam_duplicates": True, "am_antiinvite": True, "am_antiinvite_action": "delete,mute", "am_antiinvite_mute_dur": "1h", "am_antilink": True, "am_antilink_action": "delete", "am_antilink_allowed_domains": TRUSTED_DOMAIN_PRESET, "am_caps": True, "am_caps_percent": 65, "am_caps_minlen": 6, "am_caps_action": "delete", "am_mentions": True, "am_mentions_max": 4, "am_mentions_action": "warn,mute", "am_mentions_mute_dur": "30m", "am_emojispam": True, "am_emojispam_max": 8, "am_emojispam_action": "delete", "am_imagespam": True, "am_imagespam_count": 3, "am_imagespam_interval": 8, "am_imagespam_action": "delete"},
}

PRESET_MAP = {"economy": ECONOMY_PRESETS, "automod": AUTOMOD_PRESETS}

PRESET_META = {
    "economy": {
        "casual": {
            "description": "Щедріші нагороди, вищі ставки й швидкий старт.",
            "fit": "Підійде лайтовим серверам, де важлива легка економіка й швидкий фан.",
        },
        "balanced": {
            "description": "Нейтральний дефолт без перекосу в жорсткість чи халяву.",
            "fit": "Підійде більшості серверів як базовий стартовий режим.",
        },
        "grindy": {
            "description": "Повільніший прогрес, менше халяви й більше фарму.",
            "fit": "Підійде серверам, де прогрес має відчуватись довшим і важчим.",
        },
        "community": {
            "description": "Акцент на квести, сезон і спільні системи сервера.",
            "fit": "Підійде активним ком'юніті, де важлива групова участь, а не тільки особистий фарм.",
        },
        "competitive": {
            "description": "Жорсткіша економіка з акцентом на ризик і конкуренцію.",
            "fit": "Підійде серверам, де хочеться напруги, лідерборду й боротьби за позиції.",
        },
        "creator": {
            "description": "Більше руху, фонду й квестів, без сезону як основного стрижня.",
            "fit": "Підійде creator/community серверам, де економіка підтримує активність навколо контенту.",
        },
        "roleplay": {
            "description": "Помірна економіка з банком, сезоном і довшими циклами.",
            "fit": "Підійде roleplay або лорним серверам, де важливі темп, статус і довша дистанція прогресу.",
        },
    },
    "automod": {
        "relaxed": {
            "description": "М'який фільтр без зайвого тиску на звичайний чат.",
            "fit": "Підійде дружнім серверам, де не хочеться агресивного автомоду.",
        },
        "balanced": {
            "description": "Помірний контроль спаму, лінків і шуму.",
            "fit": "Підійде більшості серверів як базовий адекватний режим автомоду.",
        },
        "strict": {
            "description": "Жорсткий антиспам і швидка реакція на токсичний шум.",
            "fit": "Підійде великим або проблемним серверам із високим ризиком сміття.",
        },
    },
}

AUTOMOD_DEFAULTS = {key: False for key in AUTOMOD_MODULES}
for values in AUTOMOD_SETTINGS.values():
    for setting_key, meta in values.items():
        AUTOMOD_DEFAULTS[setting_key] = meta["default"]
AUTOMOD_DEFAULTS.update({
    "am_antispam_duplicates": False,
    "am_antiinvite_allowed_servers": [],
    "am_antilink_allowed_domains": [],
    "am_whitelist_channels": [],
    "am_whitelist_roles": [],
    "automod_rules": [],
})

LOG_DEFAULTS = {key: None for mapping in LOG_TYPES.values() for key in mapping}
LOG_DEFAULTS.update({"log_whitelist_channels": [], "log_whitelist_roles": [], "stats_interval_days": 7})
SERVER_DEFAULTS = {"command_restrictions": {}}
WARNING_DEFAULTS = {"warn_escalation": [], "warn_decay_days": 0}

WELCOME_KEYS = {
    "welcome_channel_id", "welcome_text", "welcome_image_enabled", "welcome_font_color", "welcome_font_name", "welcome_outline_color", "welcome_bg_url", "welcome_bg_color",
    "goodbye_channel_id", "goodbye_text", "goodbye_image_enabled", "goodbye_font_color", "goodbye_font_name", "goodbye_outline_color", "goodbye_bg_url", "goodbye_bg_color",
    "boost_channel_id", "boost_text", "boost_image_enabled", "boost_font_color", "boost_font_name", "boost_outline_color", "boost_bg_url", "boost_bg_color", "boost_role_id",
}

ECONOMY_RUNTIME_KEYS = {
    "fund_current",
    "season_start",
    "season_number",
    "season_history",
}


def _strip_code_block(raw: str) -> str:
    value = raw.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value)
        value = re.sub(r"```$", "", value.strip())
    return value.strip()


def _status_icon(enabled: bool) -> str:
    return E_CHECK if enabled else E_CROSS


def _trim_preview(values: list[str], limit: int = 3) -> str:
    if not values:
        return f"{E_CROSS} немає"
    preview = ", ".join(values[:limit])
    if len(values) > limit:
        preview += f" +{len(values) - limit}"
    return preview


def _summarize_patch_keys(patch: dict, limit: int = 6) -> str:
    keys = [f"`{key}`" for key in patch]
    return _trim_preview(keys, limit=limit)


def _stringify_value(value) -> str:
    if isinstance(value, bool):
        return "увімкнено" if value else "вимкнено"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if isinstance(value, list):
        if not value:
            return "[]"
        if len(value) <= 3:
            return json.dumps(value, ensure_ascii=False)
        return f"[{len(value)} елементів]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        keys = list(value)[:3]
        suffix = "" if len(value) <= 3 else f" +{len(value) - 3}"
        return "{" + ", ".join(str(key) for key in keys) + "}" + suffix
    if value in (None, ""):
        return "немає"
    return str(value)


def _build_diff_lines(current: dict, patch: dict, limit: int = 5) -> list[str]:
    lines = []
    for key, new_value in patch.items():
        old_value = current.get(key)
        if old_value == new_value:
            continue
        lines.append(f"`{key}`: `{_stringify_value(old_value)}` -> `{_stringify_value(new_value)}`")
    if len(lines) > limit:
        lines = lines[:limit] + [f"+{len(lines) - limit} змін"]
    return lines or ["Ефективних змін значень не виявлено."]


def _preset_lines(module: str) -> list[str]:
    presets = PRESET_MAP.get(module, {})
    meta_map = PRESET_META.get(module, {})
    if not presets:
        return [f"{E_CROSS} Немає пресетів"]
    lines = []
    for name in presets:
        desc = meta_map.get(name, {}).get("description")
        lines.append(f"`{name}` — {desc}" if desc else f"`{name}`")
    return lines


def _export_payload(module: str, payload: dict) -> dict:
    if module == "economy":
        return {key: value for key, value in payload.items() if key not in ECONOMY_RUNTIME_KEYS}
    return payload


def _format_shop_role(role_entry: dict) -> str:
    return f"<@&{role_entry['role_id']}> -> `{role_entry['price']}`"


def _unwrap_config_payload(module: str, payload):
    data = _ensure_patch_dict(payload)
    if {"module", "version", "patch"}.issubset(data.keys()):
        if data["module"] != module:
            raise ValueError(f"Модуль у JSON-обгортці `{data['module']}` не збігається з вибраним модулем `{module}`.")
        if data["version"] != CONFIG_SCHEMA_VERSION:
            raise ValueError(f"Непідтримувана версія конфіга `{data['version']}`.")
        return _ensure_patch_dict(data["patch"])
    return data


def _is_color(value: str) -> bool:
    return bool(re.fullmatch(r"#?[0-9A-Fa-f]{6}", value))


def _ensure_patch_dict(payload):
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Імпорт очікує непорожній JSON-об'єкт.")
    return payload


def _validate_economy_patch(payload: dict) -> dict:
    result = {}
    for key, value in _ensure_patch_dict(payload).items():
        if key not in DEFAULT_ECO:
            raise ValueError(f"`{key}` не є підтримуваним параметром економіки.")
        if key in ECONOMY_RUNTIME_KEYS:
            raise ValueError(f"`{key}` є службовим runtime-станом і не редагується через `/config`.")
        if key == "msg_earn":
            if not isinstance(value, list) or len(value) != 2 or any(not isinstance(item, int) or item < 0 for item in value) or value[0] > value[1]:
                raise ValueError("`msg_earn` має бути у форматі [min, max].")
        elif key == "enabled_minigames":
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError("`enabled_minigames` має бути списком рядків.")
            value = list(dict.fromkeys(value))
        elif key == "shop_roles":
            if not isinstance(value, list) or any(not isinstance(item, dict) or not isinstance(item.get("role_id"), int) or not isinstance(item.get("price"), int) for item in value):
                raise ValueError("`shop_roles` має містити об'єкти з `role_id` і `price`.")
            seen_roles = set()
            normalized = []
            for item in value:
                role_id = item["role_id"]
                price = item["price"]
                if role_id <= 0 or price < 0:
                    raise ValueError("У `shop_roles` `role_id` має бути додатним, а `price` — невід'ємним.")
                if role_id in seen_roles:
                    raise ValueError("`shop_roles` не може містити дублікати ролей.")
                seen_roles.add(role_id)
                normalized.append({"role_id": role_id, "price": price})
            value = normalized
        elif key == "season_winner_roles":
            if not isinstance(value, dict) or any(not isinstance(sub_key, str) or not isinstance(sub_value, int) for sub_key, sub_value in value.items()):
                raise ValueError("`season_winner_roles` має бути об'єктом string -> int.")
            if any(not sub_key.isdigit() or int(sub_key) <= 0 or sub_value <= 0 for sub_key, sub_value in value.items()):
                raise ValueError("`season_winner_roles` має використовувати додатні місця та ID ролей.")
        elif key in {"work_type"}:
            if value not in {"simple", "complex", "both"}:
                raise ValueError("`work_type` має бути simple, complex або both.")
        elif key in {"bank_interest_interval"}:
            if value not in {"daily", "weekly"}:
                raise ValueError("`bank_interest_interval` має бути daily або weekly.")
        elif key in {"transfer_tax_percent"}:
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 50:
                raise ValueError("`transfer_tax_percent` має бути цілим числом від 0 до 50.")
        elif key in {"transfer_daily_limit", "fund_goal", "fund_current", "season_start_bonus", "season_start", "auction_anti_snipe_seconds"}:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"`{key}` має бути невід'ємним цілим числом.")
        elif key in {"season_duration_days", "season_number"}:
            minimum = 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"`{key}` має бути цілим числом >= {minimum}.")
        elif key in {"auction_channel_id", "season_announce_channel_id"}:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"`{key}` має бути ID каналу або 0.")
        elif key in {"quests_daily_count", "quests_weekly_count", "quests_daily_reward", "quests_weekly_reward", "quests_target_multiplier"}:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"`{key}` must be a non-negative integer.")
        elif key == "season_history":
            if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                raise ValueError("`season_history` має бути списком об'єктів.")
        elif key == "bank_interest_rate":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or value > 100:
                raise ValueError("`bank_interest_rate` має бути числом від 0 до 100.")
        else:
            default = DEFAULT_ECO[key]
            if isinstance(default, list):
                if not isinstance(value, list):
                    raise ValueError(f"`{key}` має бути списком.")
            elif isinstance(default, dict):
                if not isinstance(value, dict):
                    raise ValueError(f"`{key}` має бути об'єктом.")
            if isinstance(default, bool) and not isinstance(value, bool):
                raise ValueError(f"`{key}` має бути булевим значенням.")
            if isinstance(default, int) and not isinstance(default, bool) and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"`{key}` має бути цілим числом.")
            if isinstance(default, float) and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ValueError(f"`{key}` має бути числом.")
            if isinstance(default, str) and not isinstance(value, str):
                raise ValueError(f"`{key}` має бути рядком.")
        result[key] = value
    if "work_min" in result and "work_max" in result and result["work_min"] > result["work_max"]:
        raise ValueError("`work_min` має бути <= `work_max`.")
    return result


def _validate_automod_patch(payload: dict) -> dict:
    result = {}
    for key, value in _ensure_patch_dict(payload).items():
        if key not in AUTOMOD_DEFAULTS:
            raise ValueError(f"`{key}` не є підтримуваним параметром автомоду.")
        if key.endswith("_action"):
            if not isinstance(value, str):
                raise ValueError(f"`{key}` має містити warn/mute/delete.")
            actions = [action.strip() for action in value.split(",") if action.strip()]
            if not actions or any(action not in {"warn", "mute", "delete"} for action in actions):
                raise ValueError(f"`{key}` має містити warn/mute/delete.")
        elif key in {"am_antiinvite_allowed_servers"}:
            if not isinstance(value, list) or any(not isinstance(item, (int, dict)) for item in value):
                raise ValueError("`am_antiinvite_allowed_servers` має бути списком ID або об'єктів.")
        elif key in {"am_antilink_allowed_domains"}:
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError("`am_antilink_allowed_domains` має бути списком рядків.")
        elif key in {"am_whitelist_channels", "am_whitelist_roles"}:
            if not isinstance(value, list) or any(not isinstance(item, int) for item in value):
                raise ValueError(f"`{key}` має бути списком цілих чисел.")
        elif key == "automod_rules":
            if not isinstance(value, list):
                raise ValueError("`automod_rules` має бути списком об'єктів правил із `trigger`.")
            for item in value:
                if not isinstance(item, dict) or not isinstance(item.get("trigger"), str):
                    raise ValueError("`automod_rules` має бути списком об'єктів правил із `trigger`.")
                if item.get("target", "both") not in {"message", "profile", "both"}:
                    raise ValueError("`automod_rules[].target` має бути message/profile/both.")
                if item.get("match", "contains") not in {"contains", "exact"}:
                    raise ValueError("`automod_rules[].match` має бути contains/exact.")
                for list_key in ("only_channels", "ignore_channels", "only_roles", "ignore_roles"):
                    if list_key in item and (not isinstance(item[list_key], list) or any(not isinstance(entry, int) for entry in item[list_key])):
                        raise ValueError(f"`automod_rules[].{list_key}` має бути списком цілих чисел.")
                if "log_channel_id" in item and item["log_channel_id"] is not None and not isinstance(item["log_channel_id"], int):
                    raise ValueError("`automod_rules[].log_channel_id` має бути int або null.")
                if "response_text" in item and not isinstance(item["response_text"], str):
                    raise ValueError("`automod_rules[].response_text` має бути рядком.")
                if "mute_dur" in item and not isinstance(item["mute_dur"], str):
                    raise ValueError("`automod_rules[].mute_dur` має бути рядком.")
        else:
            default = AUTOMOD_DEFAULTS[key]
            if isinstance(default, bool) and not isinstance(value, bool):
                raise ValueError(f"`{key}` має бути булевим значенням.")
            if isinstance(default, int) and not isinstance(default, bool) and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"`{key}` має бути цілим числом.")
            if isinstance(default, str) and not isinstance(value, str):
                raise ValueError(f"`{key}` має бути рядком.")
        result[key] = value
    return result


def _validate_simple_patch(payload: dict, defaults: dict, module_name: str) -> dict:
    result = {}
    for key, value in _ensure_patch_dict(payload).items():
        if key not in defaults:
            raise ValueError(f"`{key}` is not a supported {module_name} setting.")
        default = defaults[key]
        if isinstance(default, list):
            if not isinstance(value, list):
                raise ValueError(f"`{key}` має бути списком.")
        elif isinstance(default, dict):
            if not isinstance(value, dict):
                raise ValueError(f"`{key}` має бути об'єктом.")
        elif default is None:
            if value is not None and not isinstance(value, int):
                raise ValueError(f"`{key}` має бути int або null.")
        elif isinstance(default, bool) and not isinstance(value, bool):
            raise ValueError(f"`{key}` має бути булевим значенням.")
        elif isinstance(default, int) and not isinstance(default, bool) and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"`{key}` має бути цілим числом.")
        result[key] = value
    return result


def _validate_server_patch(payload: dict) -> dict:
    result = {}
    for key, value in _ensure_patch_dict(payload).items():
        if key == "command_restrictions":
            if not isinstance(value, dict):
                raise ValueError("`command_restrictions` має бути об'єктом.")
            for cmd_name, channels in value.items():
                if not isinstance(cmd_name, str) or not isinstance(channels, list) or any(not isinstance(channel_id, int) for channel_id in channels):
                    raise ValueError("`command_restrictions` має зберігати назви команд і списки ID каналів.")
            value = normalize_command_restrictions(value)
        else:
            raise ValueError(f"`{key}` не є підтримуваним параметром сервера.")
        result[key] = value
    return result


def _validate_warning_patch(payload: dict) -> dict:
    result = {}
    for key, value in _ensure_patch_dict(payload).items():
        if key == "warn_decay_days":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("`warn_decay_days` має бути цілим числом.")
        elif key == "warn_escalation":
            if not isinstance(value, list):
                raise ValueError("`warn_escalation` має бути списком.")
            for item in value:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("count"), int)
                    or item.get("action") not in {"mute", "kick", "ban"}
                    or not isinstance(item.get("duration", ""), str)
                ):
                    raise ValueError("Елементи `warn_escalation` мають містити `count`, `action`, `duration`.")
        else:
            raise ValueError(f"`{key}` не є підтримуваним параметром попереджень.")
        result[key] = value
    return result


def _validate_logs_patch(payload: dict) -> dict:
    result = {}
    for key, value in _ensure_patch_dict(payload).items():
        if key not in LOG_DEFAULTS:
            raise ValueError(f"`{key}` не є підтримуваним параметром логів.")
        if key == "stats_interval_days":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("`stats_interval_days` має бути цілим числом.")
        elif key in {"log_whitelist_channels", "log_whitelist_roles"}:
            if not isinstance(value, list) or any(not isinstance(item, int) for item in value):
                raise ValueError(f"`{key}` має бути списком цілих чисел.")
        elif value is not None and not isinstance(value, int):
            raise ValueError(f"`{key}` має бути int або null.")
        result[key] = value
    return result


def _validate_welcome_patch(payload: dict) -> dict:
    result = {}
    for key, value in _ensure_patch_dict(payload).items():
        if key not in WELCOME_KEYS:
            raise ValueError(f"`{key}` не є підтримуваним параметром привітання.")
        if key.endswith("_channel_id") or key == "boost_role_id":
            if value is not None and not isinstance(value, int):
                raise ValueError(f"`{key}` має бути int або null.")
        elif key.endswith("_text") or key.endswith("_font_name") or key.endswith("_bg_url"):
            if not isinstance(value, str):
                raise ValueError(f"`{key}` має бути рядком.")
        elif key.endswith("_image_enabled"):
            if not isinstance(value, bool):
                raise ValueError(f"`{key}` має бути булевим значенням.")
        elif key.endswith("_font_color") or key.endswith("_outline_color") or key.endswith("_bg_color"):
            if not isinstance(value, str) or not _is_color(value):
                raise ValueError(f"`{key}` має бути HEX-кольором.")
            value = value if value.startswith("#") else f"#{value}"
        result[key] = value
    return result


async def _load_payloads(guild_id: int) -> dict[str, dict]:
    settings = await _col.find_one({"_id": guild_id}) or {}
    restrictions = normalize_command_restrictions(settings.get("command_restrictions"))
    if restrictions != settings.get("command_restrictions", {}):
        settings["command_restrictions"] = restrictions
        await _col.update_one({"_id": guild_id}, {"$set": {"command_restrictions": restrictions}}, upsert=True)
    payloads = {
        "server": {"command_restrictions": restrictions},
        "economy": get_eco(settings),
        "automod": {key: settings.get(key, default) for key, default in AUTOMOD_DEFAULTS.items()},
        "logs": {key: settings.get(key, default) for key, default in LOG_DEFAULTS.items()},
        "warnings": {**WARNING_DEFAULTS, **{key: settings.get(key, default) for key, default in WARNING_DEFAULTS.items()}},
        "welcome": await get_greetings_settings(guild_id),
    }
    return payloads


async def _apply_patch_to_module(interaction: discord.Interaction, module: str, payload: dict) -> int:
    if module == "economy":
        patch = _validate_economy_patch(_unwrap_config_payload(module, payload))
        await save_eco(interaction.guild.id, {f"economy.{key}": value for key, value in patch.items()})
        return len(patch)
    if module == "automod":
        patch = _validate_automod_patch(_unwrap_config_payload(module, payload))
        await _col.update_one({"_id": interaction.guild.id}, {"$set": patch}, upsert=True)
        await reload_guild_automod_cache(interaction.guild.id)
        return len(patch)
    if module == "server":
        patch = _validate_server_patch(_unwrap_config_payload(module, payload))
        await _col.update_one({"_id": interaction.guild.id}, {"$set": patch}, upsert=True)
        if "command_restrictions" in patch and hasattr(interaction.client, "reload_restrictions"):
            await interaction.client.reload_restrictions(interaction.guild.id)
        return len(patch)
    if module == "logs":
        patch = _validate_logs_patch(_unwrap_config_payload(module, payload))
        await _col.update_one({"_id": interaction.guild.id}, {"$set": patch}, upsert=True)
        return len(patch)
    if module == "warnings":
        patch = _validate_warning_patch(_unwrap_config_payload(module, payload))
        await _col.update_one({"_id": interaction.guild.id}, {"$set": patch}, upsert=True)
        return len(patch)
    if module == "welcome":
        patch = _validate_welcome_patch(_unwrap_config_payload(module, payload))
        await _col.update_one({"_id": interaction.guild.id}, {"$set": patch}, upsert=True)
        return len(patch)
    raise ValueError("Непідтримуваний модуль.")


def _summary_lines(module: str, payload: dict) -> list[str]:
    if module == "economy":
        return [
            f"Стан {_status_icon(payload.get('enabled', False))}",
            f"Щоденна `{payload.get('daily_amount', 0)}` | Робота `{payload.get('work_min', 0)}-{payload.get('work_max', 0)}`",
            f"Пограбування {_status_icon(payload.get('rob_enabled', False))} | Гемблінг {_status_icon(payload.get('gambling_enabled', False))}",
            f"Сезон {_status_icon(payload.get('season_enabled', False))} | Квести {_status_icon(payload.get('quests_enabled', False))} | Ролі магазину `{len(payload.get('shop_roles', []))}`",
            f"Податок на переказ `{payload.get('transfer_tax_percent', 0)}%` | Ціль фонду `{payload.get('fund_goal', 0):,}` | Антиснайп `{payload.get('auction_anti_snipe_seconds', 30)}с`",
        ]
    if module == "automod":
        enabled = sum(1 for key in AUTOMOD_MODULES if payload.get(key, False))
        return [
            f"Модулі `{enabled}/{len(AUTOMOD_MODULES)}`",
            f"Довірені домени `{len(payload.get('am_antilink_allowed_domains', []))}`",
            f"Правила `{len(payload.get('automod_rules', []))}`",
        ]
    if module == "server":
        restricted = len([key for key, value in payload.get("command_restrictions", {}).items() if value])
        return [f"Обмежених команд `{restricted}`", "XP та level-up керуються через `/xp_setup`."]
    if module == "logs":
        configured = len([key for key, value in payload.items() if key not in {'log_whitelist_channels', 'log_whitelist_roles', 'stats_interval_days'} and value])
        return [f"Налаштованих лог-каналів `{configured}`", f"Інтервал статистики `{payload.get('stats_interval_days', 7)}` днів", f"Дозволені канали `{len(payload.get('log_whitelist_channels', []))}` / ролі `{len(payload.get('log_whitelist_roles', []))}`"]
    if module == "warnings":
        rules = payload.get("warn_escalation", [])
        return [f"Ескалацій `{len(rules)}`", f"Спадання `{payload.get('warn_decay_days', 0)}` днів", f"Верхня дія `{rules[0]['action']}`" if rules else f"{E_CROSS} Без ескалації"]
    return [
        f"Привітання {'увімкнено' if payload.get('welcome_channel_id') else 'вимкнено'}",
        f"Прощання {'увімкнено' if payload.get('goodbye_channel_id') else 'вимкнено'}",
        f"Бусти {'увімкнено' if payload.get('boost_channel_id') else 'вимкнено'}",
    ]


def _simulate_automod_message(payload: dict, content: str) -> list[str]:
    results = []
    text = content or ""

    if payload.get("am_antiinvite") and _INVITE_RE.search(text):
        results.append(f"Запрошення -> `{payload.get('am_antiinvite_action', 'delete')}`")

    if payload.get("am_antilink") and _URL_RE.search(text):
        domains = [domain.lower() for domain in payload.get("am_antilink_allowed_domains", [])]
        blocked = False
        for url in _URL_RE.findall(text):
            domain = re.sub(r'https?://', '', url).split('/')[0].lower().lstrip("www.")
            if not any(domain == allowed or domain.endswith("." + allowed) for allowed in domains + ["cdn.discordapp.com", "media.discordapp.net"]):
                blocked = True
                break
        if blocked:
            results.append(f"Посилання -> `{payload.get('am_antilink_action', 'delete')}`")

    if payload.get("am_caps"):
        letters = [char for char in text if char.isalpha()]
        if letters:
            ratio = sum(1 for char in letters if char.isupper()) / len(letters) * 100
            if len(letters) >= payload.get("am_caps_minlen", 8) and ratio >= payload.get("am_caps_percent", 70):
                results.append(f"Caps lock -> `{payload.get('am_caps_action', 'delete')}`")

    if payload.get("am_mentions"):
        mention_count = text.count("<@") + text.count("@everyone") * 5 + text.count("@here") * 5
        if mention_count >= payload.get("am_mentions_max", 5):
            results.append(f"Масові згадки -> `{payload.get('am_mentions_action', 'warn')}`")

    if payload.get("am_emojispam"):
        emoji_count = len(_EMOJI_RE.findall(text))
        if emoji_count >= payload.get("am_emojispam_max", 10):
            results.append(f"Спам емодзі -> `{payload.get('am_emojispam_action', 'delete')}`")

    rule = find_matching_rule(payload.get("automod_rules", []), text, target="message")
    if rule:
        results.append(f"Кастомне правило `{rule.get('trigger', '?')}` -> `{rule.get('action', 'warn')}`")

    return results or ["Жодне статичне правило не спрацювало. Перевірки спаму й зображень зі станом тут не моделюються."]


def _build_embed(guild: discord.Guild, payloads: dict[str, dict], module: str | None) -> discord.Embed:
    if module is None:
        embed = surface_embed(
            "admin",
            f"{E_SETTING} /config",
            "Керуйте модулями сервера: огляд, пресети, імпорт, експорт і швидкі редактори.",
        )
        for key, meta in MODULE_META.items():
            add_section(embed, f"{meta['emoji']} {meta['label']}", _summary_lines(key, payloads[key]))
        set_surface_footer(embed, "admin", guild.name)
        return embed

    meta = MODULE_META[module]
    embed = surface_embed(
        "admin",
        f"{meta['emoji']} {meta['label']}",
        f"Огляд поточного стану, пресети, імпорт, експорт і швидкі редактори для `{meta['command']}`.",
    )
    add_section(embed, "Поточний стан", _summary_lines(module, payloads[module]))

    if module == "economy":
        payload = payloads[module]
        add_section(
            embed,
            "Системи",
            [
                compact_kv("Квести", f"денні `{payload.get('quests_daily_count', 0)}` / тижневі `{payload.get('quests_weekly_count', 0)}`"),
                compact_kv("Сезон", f"`{payload.get('season_duration_days', 0)}` днів • ролей `{len(payload.get('season_winner_roles', {}))}`"),
                compact_kv("Фонд", f"ціль `{payload.get('fund_goal', 0):,}`"),
                compact_kv("Ролі магазину", f"`{len(payload.get('shop_roles', []))}` • ліміт переказу `{payload.get('transfer_daily_limit', 0):,}`"),
            ],
        )
    if module == "automod":
        domains = [f"`{domain}`" for domain in payloads[module].get("am_antilink_allowed_domains", [])]
        words = [f"`{rule.get('trigger', '')}`" for rule in payloads[module].get("automod_rules", []) if rule.get("trigger")]
        add_section(embed, "Довірені домени і правила", [compact_kv("Домени", _trim_preview(domains)), compact_kv("Правила", _trim_preview(words))])
    if module == "server":
        restricted = [f"`/{name}`" for name, channels in payloads[module].get("command_restrictions", {}).items() if channels]
        add_section(embed, "Обмеження", [_trim_preview(restricted, limit=5)])

    add_section(embed, "Пресети", _preset_lines(module))
    set_surface_footer(embed, "admin", "Імпорт приймає лише часткові JSON-патчі.")
    return embed


class ModuleSelect(discord.ui.Select):
    def __init__(self, selected_module: str | None):
        options = [
            discord.SelectOption(
                label=meta["label"],
                value=key,
                emoji=discord.PartialEmoji.from_str(meta["emoji"]),
                default=key == selected_module,
            )
            for key, meta in MODULE_META.items()
        ]
        super().__init__(placeholder="Оберіть модуль для /config...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await ConfigView.refresh_message(interaction, self.values[0])


class PresetSelect(discord.ui.Select):
    def __init__(self, module: str):
        options = []
        meta_map = PRESET_META.get(module, {})
        for name in PRESET_MAP[module]:
            description = meta_map.get(name, {}).get("description", "")
            options.append(discord.SelectOption(label=name, value=name, description=description[:100] if description else None))
        super().__init__(placeholder="Застосувати пресет...", min_values=1, max_values=1, options=options, row=1)
        self.module = module

    async def callback(self, interaction: discord.Interaction):
        view: ConfigView = self.view
        patch = PRESET_MAP[self.module][self.values[0]]
        diff_lines = _build_diff_lines(view.payloads[self.module], patch)
        changed = await _apply_patch_to_module(interaction, self.module, patch)
        await ConfigView.refresh_message(
            interaction,
            self.module,
            notice=(
                f"{E_CHECK} Пресет `{self.values[0]}` застосовано. Оновлено `{changed}` ключів: {_summarize_patch_keys(patch)}.\n"
                + "\n".join(f"- {line}" for line in diff_lines)
            ),
        )


class ImportModal(discord.ui.Modal):
    patch_input = discord.ui.TextInput(label="JSON-патч", style=discord.TextStyle.paragraph, placeholder='{"daily_amount": 300}', max_length=4000, required=True)

    def __init__(self, module: str, current_payload: dict):
        super().__init__(title=f"Імпорт: {MODULE_META[module]['label']}")
        self.module = module
        self.current_payload = current_payload

    async def on_submit(self, interaction: discord.Interaction):
        try:
            payload = json.loads(_strip_code_block(self.patch_input.value))
            changed = await _apply_patch_to_module(interaction, self.module, payload)
        except json.JSONDecodeError as exc:
            return await interaction.response.send_message(f"{E_CROSS} Некоректний JSON: `{exc.msg}`.", ephemeral=True)
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        patch = _unwrap_config_payload(self.module, payload)
        diff_lines = _build_diff_lines(self.current_payload, patch)
        await ConfigView.refresh_message(
            interaction,
            self.module,
            notice=(
                f"{E_CHECK} Імпорт застосовано. Оновлено `{changed}` ключів: {_summarize_patch_keys(patch)}.\n"
                + "\n".join(f"- {line}" for line in diff_lines)
            ),
        )


class ImportButton(discord.ui.Button):
    def __init__(self, module: str, current_payload: dict):
        super().__init__(label="Імпорт патча", style=discord.ButtonStyle.primary, row=2)
        self.module = module
        self.current_payload = current_payload

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ImportModal(self.module, self.current_payload))


class ExportButton(discord.ui.Button):
    def __init__(self, module: str, payload: dict):
        super().__init__(label="Експорт JSON", style=discord.ButtonStyle.secondary, row=2)
        self.module = module
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        envelope = {
            "module": self.module,
            "version": CONFIG_SCHEMA_VERSION,
            "patch": _export_payload(self.module, self.payload),
        }
        raw = json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")
        file = discord.File(io.BytesIO(raw), filename=f"{self.module}_config.json")
        await interaction.response.send_message(content=f"{E_CHECK} Експорт `{self.module}` у схемі v{CONFIG_SCHEMA_VERSION}.", file=file, ephemeral=True)


class EconomyPolicyModal(discord.ui.Modal, title="Швидка політика економіки"):
    daily_amount = discord.ui.TextInput(label="Daily сума", max_length=10)
    work_range = discord.ui.TextInput(label="Діапазон work (min-max)", placeholder="50-400", max_length=20)
    transfer_tax = discord.ui.TextInput(label="Податок на переказ %", max_length=3)
    transfer_limit = discord.ui.TextInput(label="Ліміт переказу на день", max_length=12)
    bank_interest = discord.ui.TextInput(label="Відсоток банку / період", placeholder="1.5 weekly", max_length=20)

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        self.daily_amount.default = str(payload.get("daily_amount", 0))
        self.work_range.default = f"{payload.get('work_min', 0)}-{payload.get('work_max', 0)}"
        self.transfer_tax.default = str(payload.get("transfer_tax_percent", 0))
        self.transfer_limit.default = str(payload.get("transfer_daily_limit", 0))
        self.bank_interest.default = f"{payload.get('bank_interest_rate', 0)} {payload.get('bank_interest_interval', 'daily')}"

    async def on_submit(self, interaction: discord.Interaction):
        raw_range = self.work_range.value.strip().replace(" ", "")
        if "-" not in raw_range:
            return await interaction.response.send_message(f"{E_CROSS} Діапазон work має бути у форматі `min-max`.", ephemeral=True)
        low_str, high_str = raw_range.split("-", 1)
        if not low_str.isdigit() or not high_str.isdigit():
            return await interaction.response.send_message(f"{E_CROSS} Діапазон work має містити лише числа.", ephemeral=True)
        interest_parts = self.bank_interest.value.strip().replace(",", " ").split()
        if len(interest_parts) != 2:
            return await interaction.response.send_message(f"{E_CROSS} Відсоток банку має бути у форматі `1.5 weekly`.", ephemeral=True)
        try:
            patch = {
                "daily_amount": int(self.daily_amount.value),
                "work_min": int(low_str),
                "work_max": int(high_str),
                "transfer_tax_percent": int(self.transfer_tax.value),
                "transfer_daily_limit": int(self.transfer_limit.value),
                "bank_interest_rate": float(interest_parts[0]),
                "bank_interest_interval": interest_parts[1].lower(),
            }
            changed = await _apply_patch_to_module(interaction, "economy", patch)
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        diff_lines = _build_diff_lines(self.payload, patch)
        await ConfigView.refresh_message(
            interaction,
            "economy",
            notice=f"{E_CHECK} Політику економіки оновлено. Змінено `{changed}` ключів.\n" + "\n".join(f"- {line}" for line in diff_lines),
        )


class EconomyPolicyButton(discord.ui.Button):
    def __init__(self, payload: dict):
        super().__init__(label="Швидка політика", style=discord.ButtonStyle.secondary, row=3)
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EconomyPolicyModal(self.payload))


class EconomySystemsModal(discord.ui.Modal, title="Швидкі системи економіки"):
    quests_daily = discord.ui.TextInput(label="К-сть денних квестів", max_length=4)
    quests_weekly = discord.ui.TextInput(label="К-сть тижневих квестів", max_length=4)
    season_duration = discord.ui.TextInput(label="Тривалість сезону (днів)", max_length=5)
    fund_goal = discord.ui.TextInput(label="Ціль фонду", max_length=12)
    anti_snipe = discord.ui.TextInput(label="Антиснайп аукціону (сек)", max_length=5)

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        self.quests_daily.default = str(payload.get("quests_daily_count", 0))
        self.quests_weekly.default = str(payload.get("quests_weekly_count", 0))
        self.season_duration.default = str(payload.get("season_duration_days", 30))
        self.fund_goal.default = str(payload.get("fund_goal", 0))
        self.anti_snipe.default = str(payload.get("auction_anti_snipe_seconds", 30))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            patch = {
                "quests_daily_count": int(self.quests_daily.value),
                "quests_weekly_count": int(self.quests_weekly.value),
                "season_duration_days": int(self.season_duration.value),
                "fund_goal": int(self.fund_goal.value),
                "auction_anti_snipe_seconds": int(self.anti_snipe.value),
            }
            changed = await _apply_patch_to_module(interaction, "economy", patch)
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        diff_lines = _build_diff_lines(self.payload, patch)
        await ConfigView.refresh_message(
            interaction,
            "economy",
            notice=f"{E_CHECK} Системні параметри економіки оновлено. Змінено `{changed}` ключів.\n" + "\n".join(f"- {line}" for line in diff_lines),
        )


class EconomySystemsButton(discord.ui.Button):
    def __init__(self, payload: dict):
        super().__init__(label="Швидкі системи", style=discord.ButtonStyle.secondary, row=3)
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EconomySystemsModal(self.payload))


class EconomyQuestSettingsModal(discord.ui.Modal, title="Налаштування квестів"):
    daily_reward = discord.ui.TextInput(label="Нагорода за денний квест", max_length=8)
    weekly_reward = discord.ui.TextInput(label="Нагорода за тижневий квест", max_length=8)
    target_multiplier = discord.ui.TextInput(label="Множник цілі", max_length=5)

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        self.daily_reward.default = str(payload.get("quests_daily_reward", 200))
        self.weekly_reward.default = str(payload.get("quests_weekly_reward", 800))
        self.target_multiplier.default = str(payload.get("quests_target_multiplier", 50))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            patch = {
                "quests_daily_reward": int(self.daily_reward.value),
                "quests_weekly_reward": int(self.weekly_reward.value),
                "quests_target_multiplier": int(self.target_multiplier.value),
            }
            changed = await _apply_patch_to_module(interaction, "economy", patch)
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        diff_lines = _build_diff_lines(self.payload, patch)
        await ConfigView.refresh_message(
            interaction,
            "economy",
            notice=f"{E_CHECK} Налаштування квестів оновлено. Змінено `{changed}` ключів.\n" + "\n".join(f"- {line}" for line in diff_lines),
        )


class EconomyQuestSettingsButton(discord.ui.Button):
    def __init__(self, payload: dict):
        super().__init__(label="Налаштування квестів", style=discord.ButtonStyle.secondary, row=4)
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EconomyQuestSettingsModal(self.payload))


class EconomyFundPolicyModal(discord.ui.Modal, title="Політика фонду"):
    enabled = discord.ui.TextInput(label="Фонд увімкнено (true/false)", max_length=5)
    goal = discord.ui.TextInput(label="Ціль фонду", max_length=12)

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        self.enabled.default = "true" if payload.get("fund_enabled", False) else "false"
        self.goal.default = str(payload.get("fund_goal", 1000000))

    async def on_submit(self, interaction: discord.Interaction):
        enabled_raw = self.enabled.value.strip().lower()
        if enabled_raw not in {"true", "false", "on", "off", "1", "0"}:
            return await interaction.response.send_message(f"{E_CROSS} Поле фонду має бути true/false.", ephemeral=True)
        try:
            patch = {
                "fund_enabled": enabled_raw in {"true", "on", "1"},
                "fund_goal": int(self.goal.value),
            }
            changed = await _apply_patch_to_module(interaction, "economy", patch)
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        diff_lines = _build_diff_lines(self.payload, patch)
        await ConfigView.refresh_message(
            interaction,
            "economy",
            notice=f"{E_CHECK} Політику фонду оновлено. Змінено `{changed}` ключів.\n" + "\n".join(f"- {line}" for line in diff_lines),
        )


class EconomyFundPolicyButton(discord.ui.Button):
    def __init__(self, payload: dict):
        super().__init__(label="Політика фонду", style=discord.ButtonStyle.secondary, row=4)
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EconomyFundPolicyModal(self.payload))


class EconomyAuctionPolicyModal(discord.ui.Modal, title="Політика аукціону"):
    channel_id = discord.ui.TextInput(label="ID каналу аукціону (0=off)", max_length=20)
    anti_snipe = discord.ui.TextInput(label="Антиснайп (секунди)", max_length=5)

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        self.channel_id.default = str(payload.get("auction_channel_id", 0))
        self.anti_snipe.default = str(payload.get("auction_anti_snipe_seconds", 30))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            patch = {
                "auction_channel_id": int(self.channel_id.value),
                "auction_anti_snipe_seconds": int(self.anti_snipe.value),
            }
            changed = await _apply_patch_to_module(interaction, "economy", patch)
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        diff_lines = _build_diff_lines(self.payload, patch)
        await ConfigView.refresh_message(
            interaction,
            "economy",
            notice=f"{E_CHECK} Політику аукціону оновлено. Змінено `{changed}` ключів.\n" + "\n".join(f"- {line}" for line in diff_lines),
        )


class EconomyAuctionPolicyButton(discord.ui.Button):
    def __init__(self, payload: dict):
        super().__init__(label="Політика аукціону", style=discord.ButtonStyle.secondary, row=4)
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EconomyAuctionPolicyModal(self.payload))


class EconomySeasonRolesModal(discord.ui.Modal, title="Ролі переможців сезону"):
    first = discord.ui.TextInput(label="ID ролі за 1 місце", required=False, max_length=20)
    second = discord.ui.TextInput(label="ID ролі за 2 місце", required=False, max_length=20)
    third = discord.ui.TextInput(label="ID ролі за 3 місце", required=False, max_length=20)
    fourth = discord.ui.TextInput(label="ID ролі за 4 місце", required=False, max_length=20)
    fifth = discord.ui.TextInput(label="ID ролі за 5 місце", required=False, max_length=20)

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        current = payload.get("season_winner_roles", {})
        self.first.default = str(current.get("1", "")) or None
        self.second.default = str(current.get("2", "")) or None
        self.third.default = str(current.get("3", "")) or None
        self.fourth.default = str(current.get("4", "")) or None
        self.fifth.default = str(current.get("5", "")) or None

    async def on_submit(self, interaction: discord.Interaction):
        role_map = {}
        entries = {
            "1": self.first.value.strip(),
            "2": self.second.value.strip(),
            "3": self.third.value.strip(),
            "4": self.fourth.value.strip(),
            "5": self.fifth.value.strip(),
        }
        for position, raw in entries.items():
            if not raw:
                continue
            if not raw.isdigit():
                return await interaction.response.send_message(f"{E_CROSS} Ролі сезону мають бути ID ролей або порожні поля.", ephemeral=True)
            role_map[position] = int(raw)
        try:
            changed = await _apply_patch_to_module(interaction, "economy", {"season_winner_roles": role_map})
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        diff_lines = _build_diff_lines(self.payload, {"season_winner_roles": role_map})
        await ConfigView.refresh_message(
            interaction,
            "economy",
            notice=f"{E_CHECK} Ролі переможців сезону оновлено. Змінено `{changed}` ключ.\n" + "\n".join(f"- {line}" for line in diff_lines),
        )


class EconomySeasonRolesButton(discord.ui.Button):
    def __init__(self, payload: dict):
        super().__init__(label="Ролі сезону", style=discord.ButtonStyle.secondary, row=4)
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EconomySeasonRolesModal(self.payload))


class EconomyShopRolePriceModal(discord.ui.Modal, title="Ціна ролі магазину"):
    price = discord.ui.TextInput(label="Ціна ролі", max_length=10)

    def __init__(self, payload: dict, role_id: int):
        super().__init__()
        self.payload = payload
        self.role_id = role_id
        current = next((item for item in payload.get("shop_roles", []) if item["role_id"] == role_id), None)
        if current:
            self.price.default = str(current["price"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price.value)
        except ValueError:
            return await interaction.response.send_message(f"{E_CROSS} Ціна ролі має бути цілим числом.", ephemeral=True)
        shop_roles = [dict(item) for item in self.payload.get("shop_roles", [])]
        updated = False
        for item in shop_roles:
            if item["role_id"] == self.role_id:
                item["price"] = price
                updated = True
                break
        if not updated:
            shop_roles.append({"role_id": self.role_id, "price": price})
        try:
            changed = await _apply_patch_to_module(interaction, "economy", {"shop_roles": shop_roles})
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        payloads = await _load_payloads(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_build_shop_roles_embed(payloads["economy"]),
            view=EconomyShopRolesView(payloads["economy"]),
        )
        await interaction.followup.send(f"{E_CHECK} Ролі магазину оновлено. Змінено `{changed}` ключ.", ephemeral=True)


class EconomyShopRoleAddSelect(discord.ui.RoleSelect):
    def __init__(self, payload: dict):
        super().__init__(placeholder="Оберіть роль для додавання або оновлення...", min_values=1, max_values=1, row=0)
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EconomyShopRolePriceModal(self.payload, self.values[0].id))


class EconomyShopRoleRemoveSelect(discord.ui.Select):
    def __init__(self, payload: dict):
        self.payload = payload
        options = [
            discord.SelectOption(label=f"Видалити {entry['role_id']}", value=str(entry["role_id"]), description=f"Ціна: {entry['price']}")
            for entry in payload.get("shop_roles", [])[:25]
        ]
        super().__init__(placeholder="Оберіть роль для видалення з магазину...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        shop_roles = [entry for entry in self.payload.get("shop_roles", []) if entry["role_id"] != role_id]
        try:
            changed = await _apply_patch_to_module(interaction, "economy", {"shop_roles": shop_roles})
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        payloads = await _load_payloads(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_build_shop_roles_embed(payloads["economy"]),
            view=EconomyShopRolesView(payloads["economy"]),
        )
        await interaction.followup.send(f"{E_CHECK} Роль прибрано з магазину. Змінено `{changed}` ключ.", ephemeral=True)


def _build_shop_roles_embed(payload: dict) -> discord.Embed:
    lines = [_format_shop_role(entry) for entry in payload.get("shop_roles", [])[:15]]
    if len(payload.get("shop_roles", [])) > 15:
        lines.append(f"+{len(payload['shop_roles']) - 15} ще")
    embed = surface_embed(
        "admin",
        "Ролі магазину",
        "\n".join(lines) if lines else f"{E_CROSS} Ролі магазину ще не налаштовані.",
    )
    set_surface_footer(embed, "admin", "Додайте роль, змініть її ціну або приберіть її з магазину.")
    return embed


class EconomyShopRolesBackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Назад до /config", style=discord.ButtonStyle.secondary, row=2)

    async def callback(self, interaction: discord.Interaction):
        await ConfigView.refresh_message(interaction, "economy")


class EconomyShopRolesView(discord.ui.View):
    def __init__(self, payload: dict):
        super().__init__(timeout=1800)
        self.payload = payload
        self.add_item(EconomyShopRoleAddSelect(payload))
        if payload.get("shop_roles"):
            self.add_item(EconomyShopRoleRemoveSelect(payload))
        self.add_item(EconomyShopRolesBackButton())


class EconomyShopRolesButton(discord.ui.Button):
    def __init__(self, payload: dict):
        super().__init__(label="Ролі магазину", style=discord.ButtonStyle.secondary, row=4)
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        payloads = await _load_payloads(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_build_shop_roles_embed(payloads["economy"]),
            view=EconomyShopRolesView(payloads["economy"]),
        )


class TrustedDomainsModal(discord.ui.Modal, title="Довірені домени"):
    domains_input = discord.ui.TextInput(label="Домени через кому", style=discord.TextStyle.paragraph, placeholder="youtube.com, github.com, imgur.com", required=False, max_length=1000)

    def __init__(self, current: list[str]):
        super().__init__()
        if current:
            self.domains_input.default = ", ".join(current)

    async def on_submit(self, interaction: discord.Interaction):
        domains = [part.strip().lower() for part in self.domains_input.value.split(",") if part.strip()]
        try:
            changed = await _apply_patch_to_module(interaction, "automod", {"am_antilink_allowed_domains": domains})
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        await ConfigView.refresh_message(interaction, "automod", notice=f"{E_CHECK} Довірені домени оновлено. Змінено `{changed}` ключ: `am_antilink_allowed_domains`.")


class TrustedDomainsButton(discord.ui.Button):
    def __init__(self, current: list[str]):
        super().__init__(label="Довірені домени", style=discord.ButtonStyle.secondary, row=2)
        self.current = current

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TrustedDomainsModal(self.current))


class AutomodPreviewModal(discord.ui.Modal):
    text_input = discord.ui.TextInput(label="Текст для симуляції", style=discord.TextStyle.paragraph, placeholder="Вставте повідомлення, щоб побачити які статичні правила спрацюють", max_length=2000, required=True)

    def __init__(self, payload: dict):
        super().__init__(title="Превʼю автомоду")
        self.payload = payload

    async def on_submit(self, interaction: discord.Interaction):
        lines = _simulate_automod_message(self.payload, self.text_input.value)
        await interaction.response.send_message("\n".join(f"- {line}" for line in lines), ephemeral=True)


class AutomodPreviewButton(discord.ui.Button):
    def __init__(self, payload: dict):
        super().__init__(label="Превʼю тексту", style=discord.ButtonStyle.secondary, row=3)
        self.payload = payload

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AutomodPreviewModal(self.payload))


class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Назад", style=discord.ButtonStyle.secondary, row=2)

    async def callback(self, interaction: discord.Interaction):
        await ConfigView.refresh_message(interaction, None)


class ConfigView(discord.ui.View):
    def __init__(self, guild_id: int, payloads: dict[str, dict], selected_module: str | None):
        super().__init__(timeout=1800)
        self.guild_id = guild_id
        self.payloads = payloads
        self.selected_module = selected_module
        self.add_item(ModuleSelect(selected_module))
        if selected_module is not None:
            if selected_module in PRESET_MAP:
                self.add_item(PresetSelect(selected_module))
            if selected_module == "automod":
                self.add_item(AutomodPreviewButton(payloads["automod"]))
            if selected_module == "economy":
                self.add_item(EconomyPolicyButton(payloads["economy"]))
                self.add_item(EconomySystemsButton(payloads["economy"]))
                self.add_item(EconomyQuestSettingsButton(payloads["economy"]))
                self.add_item(EconomyFundPolicyButton(payloads["economy"]))
                self.add_item(EconomyAuctionPolicyButton(payloads["economy"]))
                self.add_item(EconomySeasonRolesButton(payloads["economy"]))
                self.add_item(EconomyShopRolesButton(payloads["economy"]))
            self.add_item(ImportButton(selected_module, payloads[selected_module]))
            self.add_item(ExportButton(selected_module, payloads[selected_module]))
            if selected_module == "automod":
                self.add_item(TrustedDomainsButton(payloads["automod"].get("am_antilink_allowed_domains", [])))
            self.add_item(BackButton())

    @classmethod
    async def refresh_message(cls, interaction: discord.Interaction, module: str | None, notice: str | None = None):
        payloads = await _load_payloads(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_embed(interaction.guild, payloads, module), view=cls(interaction.guild.id, payloads, module))
        if notice:
            await interaction.followup.send(notice, ephemeral=True)


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="config", description="Єдиний центр керування модулями сервера")
    @app_commands.default_permissions(administrator=True)
    async def config_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        payloads = await _load_payloads(interaction.guild.id)
        await interaction.followup.send(embed=_build_embed(interaction.guild, payloads, None), view=ConfigView(interaction.guild.id, payloads, None), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
