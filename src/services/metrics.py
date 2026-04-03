from __future__ import annotations

from datetime import datetime, timedelta, timezone

from modules.db import get_database

db = get_database()

GLOBAL_METRICS_ID = "global"


async def inc_global_metric(metric: str, amount: int = 1) -> None:
    if not metric or amount == 0:
        return
    await db.bot_metrics.update_one(
        {"_id": GLOBAL_METRICS_ID},
        {"$inc": {metric: amount}},
        upsert=True,
    )


async def inc_global_metrics(metrics: dict[str, int]) -> None:
    payload = {key: value for key, value in metrics.items() if key and value}
    if not payload:
        return
    await db.bot_metrics.update_one(
        {"_id": GLOBAL_METRICS_ID},
        {"$inc": payload},
        upsert=True,
    )


async def set_global_timestamp(metric: str, when: datetime | None = None) -> None:
    if not metric:
        return
    stamp = when or datetime.now(timezone.utc)
    await db.bot_metrics.update_one(
        {"_id": GLOBAL_METRICS_ID},
        {"$set": {metric: stamp}},
        upsert=True,
    )


async def get_global_metrics() -> dict:
    return await db.bot_metrics.find_one({"_id": GLOBAL_METRICS_ID}) or {}


async def mark_user_active(guild_id: int, user_id: int, when: datetime | None = None) -> None:
    stamp = when or datetime.now(timezone.utc)
    await db.users.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": {"last_active_at": stamp}},
        upsert=True,
    )


async def count_active_users_since(since: datetime, guild_id: int | None = None) -> int:
    query: dict = {"last_active_at": {"$gte": since}}
    if guild_id is not None:
        query["guild_id"] = guild_id
    return await db.users.count_documents(query)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hours_ago(hours: int) -> datetime:
    return utc_now() - timedelta(hours=hours)
