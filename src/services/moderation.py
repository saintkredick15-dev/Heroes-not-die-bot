"""
moderation.py
Сервісний шар для обробки модератських покарань (Cases).
Централізовано створює Кейси (Варни, Мути, Кіки, Бани) та перевіряє Ескалацію.
"""
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
E_SHIELD = "🛡️"

async def _get_escalations(guild_id: int) -> list[dict]:
    """Повертає правила ескалації (напр. 3 варни = мут)."""
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    return settings.get("escalation_rules", [])

async def _count_active_warns(guild_id: int, user_id: int) -> int:
    """Рахує кількість активних варнів учасника."""
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
    action: str, # "warn", "mute", "kick", "ban"
    reason: str,
    duration_hours: int = None
) -> str:
    """
    Генерує Moderation Case, застосовує дію (якщо можливо), надсилає DM, 
    перевіряє ескалацію (якщо це warn).
    Повертає case_id (str).
    """
    case_id = str(uuid.uuid4())[:8]

    # Зберігаємо в БД (всі дії — warn, mute, ban — це окремі кейси)
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

    # Оновлюємо статистику
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

    # Спроба відправити DM (для кіка і бана робимо ДО самої дії)
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

    dm_embed.set_footer(text="Vangard Moderation System")
    await _send_dm(user, dm_embed)

    # ── Застосування самої дії (якщо user на сервері) ──
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
            pass # Неможливо покарати (вища роль або адмін)

    # ── Ескалація (Тільки для варнів) ──
    if action == "warn":
        warns = await _count_active_warns(guild.id, user.id)
        rules = await _get_escalations(guild.id)
        # Шукаємо правило, де count збігається з кількістю варнів
        for rule in sorted(rules, key=lambda x: x["count"]):
            if warns == rule["count"]:
                esc_action = rule.get("action", "mute")
                esc_dur = rule.get("duration", 24)
                # Автоматично створюємо новий кейс як наслідок ескалації
                await apply_case(
                    bot=bot,
                    guild=guild,
                    user=user,
                    moderator=bot.user,
                    action=esc_action,
                    reason=f"[Automod Escalation] Досягнуто {warns} попереджень. Останній Case: #{case_id}",
                    duration_hours=esc_dur if esc_action == "mute" else None
                )
                break # Тільки одну ескалацію за раз

    return case_id
