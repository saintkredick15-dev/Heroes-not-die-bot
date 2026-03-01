"""
moderation.py
Сервісний шар для обробки модератських покарань (Cases).
Централізовано створює Кейси (Варни, Мути, Кіки, Бани) та перевіряє Ескалацію.
"""
import re
import uuid
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from modules.db import get_database

db = get_database()

E_WARN  = "<:warn:1477376152191373504>"
E_MUTE  = "<:mutemicro:1476200127063396443>"
E_BAN   = "<:ban:1476199074494681170>"
E_KICK  = "🦵"
E_SHIELD = "<:shieldcheck:1477720160570839130>"


def _parse_duration(raw: str) -> int | None:
    """Парсить строку тривалості ('30m', '2h', '1d', '7d') в години (float → int).
    Повертає None якщо парсити не вдалось.
    """
    if not raw:
        return None
    raw = raw.strip().lower()
    match = re.match(r'^(\d+)\s*([mhd])$', raw)
    if not match:
        # Якщо це просто число — вважаємо що це години
        if raw.isdigit():
            return int(raw)
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm':
        return max(1, value // 60)  # мінімум 1 година
    elif unit == 'h':
        return value
    elif unit == 'd':
        return value * 24
    return None


async def _get_escalations(guild_id: int) -> list[dict]:
    """Повертає правила ескалації з warn_escalation."""
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    return settings.get("warn_escalation", [])


async def _count_active_warns(guild_id: int, user_id: int) -> int:
    return await db.cases.count_documents({
        "guild_id": guild_id,
        "user_id": user_id,
        "action": "warn"
    })


async def _send_dm(user: discord.User | discord.Member, embed: discord.Embed):
    try:
        await user.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def apply_case(
    bot: commands.Bot,
    guild: discord.Guild,
    user: discord.Member | discord.User,
    moderator: discord.Member | discord.User,
    action: str,
    reason: str,
    duration_hours: int = None
) -> str:
    case_id = str(uuid.uuid4())[:8]

    await db.cases.insert_one({
        "case_id": case_id,
        "guild_id": guild.id,
        "user_id": user.id,
        "moderator_id": moderator.id,
        "action": action,
        "reason": reason,
        "duration_hours": duration_hours,
        "timestamp": datetime.now(timezone.utc)
    })

    if action == "warn":
        await db.guild_analytics.update_one(
            {"guild_id": guild.id, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
            {"$inc": {"warns": 1}},
            upsert=True
        )

    action_texts = {
        "warn": ("Отримано попередження", E_WARN, 0xf39c12),
        "mute": ("Отримано Тайм-аут", E_MUTE, 0xe67e22),
        "kick": ("Вигнано з сервера", E_KICK, 0xe74c3c),
        "ban":  ("Заблоковано на сервері", E_BAN, 0x992d22)
    }

    title_text, emoji, color = action_texts.get(action, ("Покарання", E_SHIELD, 0xffffff))

    dm_embed = discord.Embed(
        title=f"{emoji} {title_text}",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    dm_embed.add_field(name="Сервер", value=guild.name, inline=True)
    dm_embed.add_field(name="Кейс", value=f"`#{case_id}`", inline=True)
    dm_embed.add_field(name="Причина", value=reason, inline=False)

    if action == "warn":
        warns = await _count_active_warns(guild.id, user.id)
        dm_embed.add_field(name="Активних варнів", value=f"**{warns}**", inline=False)
    elif duration_hours:
        dm_embed.add_field(name="Тривалість", value=f"{duration_hours} годин(и)", inline=False)

    await _send_dm(user, dm_embed)

    # Застосування дії
    if isinstance(user, discord.Member):
        try:
            if action == "mute":
                delta = discord.utils.utcnow() + timedelta(hours=duration_hours or 24)
                await user.timeout(delta, reason=f"Case #{case_id}: {reason}")
            elif action == "kick":
                await user.kick(reason=f"Case #{case_id}: {reason}")
            elif action == "ban":
                await user.ban(reason=f"Case #{case_id}: {reason}", delete_message_days=0)
        except discord.Forbidden:
            pass

    # Ескалація (тільки для варнів)
    if action == "warn":
        warns = await _count_active_warns(guild.id, user.id)
        rules = await _get_escalations(guild.id)
        for rule in sorted(rules, key=lambda x: x["count"]):
            if warns == rule["count"]:
                esc_action = rule.get("action", "mute")
                esc_dur_raw = rule.get("duration", "")
                esc_dur = _parse_duration(esc_dur_raw) if isinstance(esc_dur_raw, str) else esc_dur_raw
                await apply_case(
                    bot=bot,
                    guild=guild,
                    user=user,
                    moderator=bot.user,
                    action=esc_action,
                    reason=f"[Ескалація] Досягнуто {warns} попереджень. Case: #{case_id}",
                    duration_hours=esc_dur if esc_action == "mute" else None
                )
                break

    return case_id
