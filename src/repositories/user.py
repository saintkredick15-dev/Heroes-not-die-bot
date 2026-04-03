from __future__ import annotations

import discord

DEFAULT_USER: dict = {
    "xp": 0,
    "level": 1,
    "messages": 0,
    "messages_week": 0,
    "messages_month": 0,
    "voice_minutes": 0,
    "voice_minutes_week": 0,
    "voice_minutes_month": 0,
    "reactions": 0,
    "reactions_week": 0,
    "reactions_month": 0,
    "history": {},
    
    "wallet": 0,
    "bank": 0,
    "daily_streak": 0,
    "daily_last": 0,
    "work_last": 0,
    "total_earned": 0,
    "levelup_notify": True,  
    "eco_history": [] 
}

def get_level_xp(level: int) -> int:
    
    return 5 * (level ** 2) + 50 * level + 100

async def get_user(db, guild_id: int, user_id: int) -> dict:
    
    from modules.db import get_user_data
    user = await get_user_data(db, guild_id, user_id)
    if not user or user.get("guild_id") != guild_id:
        user = {"guild_id": guild_id, "user_id": user_id, **DEFAULT_USER}
        await db.users.insert_one(user)
    else:
        # Довантажуємо поля, які вповадили після останнього оновлення
        missing = {k: v for k, v in DEFAULT_USER.items() if k not in user}
        if missing:
            await db.users.update_one(
                {"guild_id": guild_id, "user_id": user_id},
                {"$set": missing},
            )
            user.update(missing)
    return user

async def update_user(
    db,
    guild_id: int,
    member: discord.Member | None,
    user_id: int,
    data: dict,
) -> None:
    # Беремо дані з Discord і записуємо в базу, потім витираємо давній кеш
    if member is not None:
        data["username"] = member.display_name
        data["avatar"] = member.display_avatar.url if member.display_avatar else None

    await db.users.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": data},
    )
    from modules.db import invalidate_user_data
    await invalidate_user_data(guild_id, user_id)

async def update_user_raw(db, guild_id: int, user_id: int, data: dict) -> None:
    # Швидкий апдейт без перевірки ознак, потім очищаємо кеш
    await db.users.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": data},
    )
    from modules.db import invalidate_user_data
    await invalidate_user_data(guild_id, user_id)
