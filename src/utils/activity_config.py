from __future__ import annotations

from typing import Any

import discord

from modules.db import get_database, invalidate_guild_settings

db = get_database()

DEFAULT_ACTIVITY = {
    "message_xp": 10,
    "reaction_xp": 2,
    "voice_xp_per_minute": 5,
    "levelup_channel_id": None,
    "levelup_ping_user": True,
    "levelup_allow_opt_out": True,
    "reward_mode": "highest_only",
    "reward_roles": [],
}

LEGACY_ECONOMY_KEYS = ("message_xp", "reaction_xp", "voice_xp_per_minute")
REWARD_MODES = {"highest_only", "stack_all"}


def _as_non_negative_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def normalize_reward_mode(value: Any) -> str:
    if isinstance(value, str) and value in REWARD_MODES:
        return value
    return DEFAULT_ACTIVITY["reward_mode"]


def normalize_reward_rules(value: Any) -> list[dict[str, int]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, int]] = []
    seen: set[tuple[int, int]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        level = item.get("level")
        role_id = item.get("role_id")
        if not isinstance(level, int) or not isinstance(role_id, int):
            continue
        if level <= 0 or role_id <= 0:
            continue
        pair = (level, role_id)
        if pair in seen:
            continue
        seen.add(pair)
        normalized.append({"level": level, "role_id": role_id})

    normalized.sort(key=lambda item: (item["level"], item["role_id"]))
    return normalized


def get_activity_config(settings: dict | None) -> dict:
    settings = settings or {}
    raw_activity = settings.get("activity")
    if not isinstance(raw_activity, dict):
        raw_activity = {}

    legacy_economy = settings.get("economy")
    if not isinstance(legacy_economy, dict):
        legacy_economy = {}

    config = dict(DEFAULT_ACTIVITY)
    config["message_xp"] = _as_non_negative_int(
        raw_activity.get("message_xp", legacy_economy.get("message_xp", DEFAULT_ACTIVITY["message_xp"])),
        DEFAULT_ACTIVITY["message_xp"],
    )
    config["reaction_xp"] = _as_non_negative_int(
        raw_activity.get("reaction_xp", legacy_economy.get("reaction_xp", DEFAULT_ACTIVITY["reaction_xp"])),
        DEFAULT_ACTIVITY["reaction_xp"],
    )
    config["voice_xp_per_minute"] = _as_non_negative_int(
        raw_activity.get(
            "voice_xp_per_minute",
            legacy_economy.get("voice_xp_per_minute", DEFAULT_ACTIVITY["voice_xp_per_minute"]),
        ),
        DEFAULT_ACTIVITY["voice_xp_per_minute"],
    )

    channel_id = raw_activity.get("levelup_channel_id", settings.get("levelup_channel_id"))
    config["levelup_channel_id"] = channel_id if isinstance(channel_id, int) and channel_id > 0 else None
    config["levelup_ping_user"] = bool(raw_activity.get("levelup_ping_user", DEFAULT_ACTIVITY["levelup_ping_user"]))
    config["levelup_allow_opt_out"] = bool(
        raw_activity.get("levelup_allow_opt_out", DEFAULT_ACTIVITY["levelup_allow_opt_out"])
    )
    config["reward_mode"] = normalize_reward_mode(raw_activity.get("reward_mode"))
    config["reward_roles"] = normalize_reward_rules(raw_activity.get("reward_roles"))
    return config


async def migrate_activity_config(guild_id: int) -> dict:
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    raw_activity = settings.get("activity")
    if not isinstance(raw_activity, dict):
        raw_activity = {}

    legacy_economy = settings.get("economy")
    if not isinstance(legacy_economy, dict):
        legacy_economy = {}

    set_doc: dict[str, Any] = {}
    unset_doc: dict[str, str] = {}

    for key in LEGACY_ECONOMY_KEYS:
        if key not in raw_activity and key in legacy_economy:
            set_doc[f"activity.{key}"] = _as_non_negative_int(legacy_economy.get(key), DEFAULT_ACTIVITY[key])
            unset_doc[f"economy.{key}"] = ""

    if "levelup_channel_id" not in raw_activity and isinstance(settings.get("levelup_channel_id"), int):
        set_doc["activity.levelup_channel_id"] = settings["levelup_channel_id"]
        unset_doc["levelup_channel_id"] = ""

    if set_doc or unset_doc:
        update: dict[str, Any] = {}
        if set_doc:
            update["$set"] = set_doc
        if unset_doc:
            update["$unset"] = unset_doc
        await db.guild_settings.update_one({"_id": guild_id}, update, upsert=True)
        await invalidate_guild_settings(guild_id)
        settings = await db.guild_settings.find_one({"_id": guild_id}) or {}

    return get_activity_config(settings)


async def save_activity_updates(guild_id: int, patch: dict[str, Any]) -> dict:
    normalized: dict[str, Any] = {}
    for key, value in patch.items():
        if key not in DEFAULT_ACTIVITY:
            continue
        if key in {"message_xp", "reaction_xp", "voice_xp_per_minute"}:
            normalized[key] = _as_non_negative_int(value, DEFAULT_ACTIVITY[key])
        elif key == "levelup_channel_id":
            normalized[key] = value if isinstance(value, int) and value > 0 else None
        elif key in {"levelup_ping_user", "levelup_allow_opt_out"}:
            normalized[key] = bool(value)
        elif key == "reward_mode":
            normalized[key] = normalize_reward_mode(value)
        elif key == "reward_roles":
            normalized[key] = normalize_reward_rules(value)

    if not normalized:
        return await migrate_activity_config(guild_id)

    set_doc = {f"activity.{key}": value for key, value in normalized.items()}
    unset_doc: dict[str, str] = {}

    if any(key in normalized for key in LEGACY_ECONOMY_KEYS):
        for key in LEGACY_ECONOMY_KEYS:
            unset_doc[f"economy.{key}"] = ""
    if "levelup_channel_id" in normalized:
        unset_doc["levelup_channel_id"] = ""

    update: dict[str, Any] = {"$set": set_doc}
    if unset_doc:
        update["$unset"] = unset_doc
    await db.guild_settings.update_one({"_id": guild_id}, update, upsert=True)
    await invalidate_guild_settings(guild_id)
    return await migrate_activity_config(guild_id)


def get_tracked_reward_role_ids(activity_config: dict) -> set[int]:
    return {rule["role_id"] for rule in activity_config.get("reward_roles", [])}


def resolve_reward_role_ids(level: int, activity_config: dict) -> set[int]:
    rules = normalize_reward_rules(activity_config.get("reward_roles"))
    if not rules or level <= 0:
        return set()

    reached = [rule for rule in rules if rule["level"] <= level]
    if not reached:
        return set()

    if normalize_reward_mode(activity_config.get("reward_mode")) == "stack_all":
        return {rule["role_id"] for rule in reached}

    highest_level = max(rule["level"] for rule in reached)
    return {rule["role_id"] for rule in reached if rule["level"] == highest_level}


async def sync_member_reward_roles(member: discord.Member, level: int, activity_config: dict) -> dict[str, int]:
    tracked_ids = get_tracked_reward_role_ids(activity_config)
    if not tracked_ids:
        return {"added": 0, "removed": 0, "failed": 0}

    desired_ids = resolve_reward_role_ids(level, activity_config)
    role_map = {role.id: role for role in member.guild.roles}
    current_ids = {role.id for role in member.roles}
    me = member.guild.me

    unresolved: set[int] = set()
    add_roles: list[discord.Role] = []
    for role_id in desired_ids:
        role = role_map.get(role_id)
        if role is None:
            unresolved.add(role_id)
            continue
        if role_id in current_ids:
            continue
        if me is None or role.managed or role >= me.top_role:
            unresolved.add(role_id)
            continue
        add_roles.append(role)

    remove_roles: list[discord.Role] = []
    if not unresolved and me is not None:
        for role in member.roles:
            if role.id not in tracked_ids or role.id in desired_ids:
                continue
            if role.managed or role >= me.top_role:
                unresolved.add(role.id)
                continue
            remove_roles.append(role)

    added = 0
    removed = 0
    failed = len(unresolved)

    if add_roles:
        try:
            await member.add_roles(*add_roles, reason="XP reward sync")
            added = len(add_roles)
        except (discord.Forbidden, discord.HTTPException):
            failed += len(add_roles)

    if remove_roles:
        try:
            await member.remove_roles(*remove_roles, reason="XP reward sync")
            removed = len(remove_roles)
        except (discord.Forbidden, discord.HTTPException):
            failed += len(remove_roles)

    return {"added": added, "removed": removed, "failed": failed}
