from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


ANALYTICS_FIELDS = (
    "messages",
    "reactions",
    "voice_minutes",
    "joins",
    "leaves",
    "tickets_opened",
    "tickets_closed",
    "warns",
    "mutes",
    "bans",
    "unbans",
    "economy_given",
)


def analytics_day_key(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%d")


def analytics_window_start(days: int, now: datetime | None = None) -> str:
    if days <= 0:
        raise ValueError("days must be positive")
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = stamp.date() - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d")


def empty_stats() -> dict[str, int]:
    return {field: 0 for field in ANALYTICS_FIELDS}


def normalize_stats(doc: dict[str, Any] | None) -> dict[str, int]:
    payload = empty_stats()
    source = doc or {}
    for field in ANALYTICS_FIELDS:
        payload[field] = int(source.get(field, 0) or 0)
    payload["net_members"] = payload["joins"] - payload["leaves"]
    payload["mod_actions_total"] = payload["warns"] + payload["mutes"] + payload["bans"] + payload["unbans"]
    return payload


async def aggregate_guild_analytics_lifetime(
    guild_id: int,
    *,
    collection,
) -> dict[str, int]:
    group_stage = {"_id": None}
    for field in ANALYTICS_FIELDS:
        group_stage[field] = {"$sum": f"${field}"}

    pipeline = [
        {"$match": {"guild_id": guild_id}},
        {"$group": group_stage},
    ]

    result: dict[str, Any] | None = None
    async for doc in collection.aggregate(pipeline):
        result = doc
        break
    return normalize_stats(result)


async def aggregate_guild_analytics(
    guild_id: int,
    days: int,
    *,
    collection,
    now: datetime | None = None,
) -> dict[str, int]:
    cutoff_date = analytics_window_start(days, now)
    group_stage = {"_id": None}
    for field in ANALYTICS_FIELDS:
        group_stage[field] = {"$sum": f"${field}"}

    pipeline = [
        {"$match": {"guild_id": guild_id, "date": {"$gte": cutoff_date}}},
        {"$group": group_stage},
    ]

    result: dict[str, Any] | None = None
    async for doc in collection.aggregate(pipeline):
        result = doc
        break
    return normalize_stats(result)


def build_site_stats_snapshot(
    *,
    guild_id: int,
    guild_name: str,
    member_count: int | None,
    icon_url: str | None,
    stats_24h: dict[str, int],
    stats_7d: dict[str, int],
    stats_30d: dict[str, int],
    now: datetime | None = None,
) -> dict[str, Any]:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "guild_id": str(guild_id),
        "name": guild_name,
        "member_count": member_count or 0,
        "icon": icon_url,
        "last_updated": stamp,
        "stats_24h": stats_24h,
        "stats_7d": stats_7d,
        "stats_30d": stats_30d,
    }
