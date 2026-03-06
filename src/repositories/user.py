"""
Централізований репозиторій для роботи з даними користувачів.
Замінює copy-paste get_user_data() в activity.py, admin.py та profile.py.
"""
from __future__ import annotations

import discord


# --- Дефолтна схема юзера (єдине місце визначення) ---
DEFAULT_USER: dict = {
    "xp": 0,
    "level": 1,
    "messages": 0,
    "voice_minutes": 0,
    "reactions": 0,
    "history": {},
    
    # Економіка
    "wallet": 0,
    "bank": 0,
    "daily_streak": 0,
    "daily_last": 0,
    "work_last": 0,
    "total_earned": 0,
    "levelup_notify": True,  # чи надсилати сповіщення про підвищення рівня
    "eco_history": [] # Наприклад: [{"action": "Work", "amount": 500, "time": 16400000}]
}


def get_level_xp(level: int) -> int:
    """Повертає кількість XP потрібну для підвищення з рівня `level`."""
    return 5 * (level ** 2) + 50 * level + 100


async def get_user(db, guild_id: int, user_id: int) -> dict:
    """
    Повертає дані юзера з БД. Якщо запису немає — створює з дефолтними значеннями.
    Гарантує, що всі поля DEFAULT_USER присутні (forward-compatible).
    """
    user = await db.users.find_one({"guild_id": guild_id, "user_id": user_id})
    if not user:
        user = {"guild_id": guild_id, "user_id": user_id, **DEFAULT_USER}
        await db.users.insert_one(user)
    else:
        # Gapfill: нові поля з DEFAULT_USER яких ще немає в документі
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
    """
    Оновлює поля юзера. Якщо передано `member` — зберігає актуальне ім'я і аватар.
    """
    if member is not None:
        data["username"] = member.display_name
        data["avatar"] = member.display_avatar.url if member.display_avatar else None

    await db.users.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": data},
    )


async def update_user_raw(db, guild_id: int, user_id: int, data: dict) -> None:
    """Оновлює поля юзера без збереження імені/аватару (для адмін-команд)."""
    await db.users.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": data},
    )
