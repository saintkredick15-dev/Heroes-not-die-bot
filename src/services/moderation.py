"""
moderation.py
Сервісний шар для обробки moderation cases: warn, mute, kick, ban,
ескалації та службового логування.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from config.constants import Emojis

from modules.db import get_database

db = get_database()

E_WARN = Emojis.WARN.value
E_MUTE = Emojis.MUTE.value
E_BAN = Emojis.BAN.value
E_KICK = Emojis.KICK.value
E_SHIELD = Emojis.SHIELD_CHECK.value

CASE_ACTION_META = {
    "warn": ("Отримано попередження", E_WARN, 0x1A1A2E),
    "mute": ("Отримано тайм-аут", E_MUTE, 0x1A1A2E),
    "kick": ("Вигнано з сервера", E_KICK, 0x1A1A2E),
    "ban": ("Заблоковано на сервері", E_BAN, 0x1A1A2E),
}


def _parse_duration_to_seconds(raw: str) -> int | None:
    """Парсить 30m / 2h / 1d у секунди. Чисте число вважається годинами."""
    if not raw:
        return None
    raw = raw.strip().lower()
    match = re.match(r"^(\d+)\s*([mhd])$", raw)
    if not match:
        if raw.isdigit():
            return int(raw) * 3600
        return None

    value, unit = int(match.group(1)), match.group(2)
    unit_map = {"m": 60, "h": 3600, "d": 86400}
    return value * unit_map[unit]


def _format_duration(seconds: int) -> str:
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days} дн."
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} год."
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} хв."
    return f"{seconds} с."


def _source_label(source: str) -> str:
    return {
        "manual": "Модераторська команда",
        "auto": "Автомод",
        "escalation": "Авто-ескалація",
    }.get(source, "Система")


def _log_key_for_source(source: str) -> str:
    return "log_mod_auto" if source in {"auto", "escalation"} else "log_mod_action"


async def _get_escalations(guild_id: int) -> list[dict]:
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    return settings.get("warn_escalation", [])


async def _count_active_warns(guild_id: int, user_id: int) -> int:
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    decay_days = settings.get("warn_decay_days", 0)

    query = {
        "guild_id": guild_id,
        "user_id": user_id,
        "action": "warn",
    }
    if decay_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=decay_days)
        query["timestamp"] = {"$gte": cutoff}

    return await db.cases.count_documents(query)


async def _send_dm(user: discord.User | discord.Member, embed: discord.Embed) -> None:
    try:
        await user.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def _send_case_log(guild: discord.Guild, log_key: str, embed: discord.Embed) -> None:
    settings = await db.guild_settings.find_one({"_id": guild.id}) or {}
    channel_id = settings.get(log_key)
    if not channel_id:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


def _build_dm_embed(
    *,
    guild: discord.Guild,
    moderator: discord.Member | discord.User,
    action: str,
    reason: str,
    case_id: str,
    source: str,
    duration_seconds: int | None,
    origin_text: str | None,
    active_warns: int | None,
) -> discord.Embed:
    title_text, emoji, color = CASE_ACTION_META.get(action, ("Покарання", E_SHIELD, 0xFFFFFF))
    embed = discord.Embed(
        title=f"{emoji} {title_text}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Сервер", value=guild.name, inline=True)
    embed.add_field(name="Case ID", value=f"`#{case_id}`", inline=True)
    embed.add_field(name="Джерело", value=_source_label(source), inline=True)
    embed.add_field(name="Модератор", value=getattr(moderator, "mention", "Система"), inline=False)
    embed.add_field(name="Причина", value=reason, inline=False)

    if origin_text:
        embed.add_field(name="Звідки", value=origin_text, inline=False)

    if active_warns is not None:
        embed.add_field(name="Активних варнів", value=f"**{active_warns}**", inline=False)

    if duration_seconds:
        until = discord.utils.utcnow() + timedelta(seconds=duration_seconds)
        embed.add_field(name="Тривалість", value=_format_duration(duration_seconds), inline=True)
        embed.add_field(name="Закінчиться", value=discord.utils.format_dt(until, "R"), inline=True)

    if source == "escalation":
        embed.set_footer(text="Покарання застосовано автоматично після досягнення порогу попереджень.")

    return embed


def _build_log_embed(
    *,
    guild: discord.Guild,
    user: discord.Member | discord.User,
    moderator: discord.Member | discord.User,
    action: str,
    reason: str,
    case_id: str,
    source: str,
    duration_seconds: int | None,
    origin_text: str | None,
    active_warns: int | None,
) -> discord.Embed:
    title_text, emoji, color = CASE_ACTION_META.get(action, ("Покарання", E_SHIELD, 0xFFFFFF))
    embed = discord.Embed(
        title=f"{emoji} {title_text}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Користувач", value=f"{getattr(user, 'mention', user)}\n`{user.id}`", inline=True)
    embed.add_field(name="Модератор", value=getattr(moderator, "mention", "Система"), inline=True)
    embed.add_field(name="Case ID", value=f"`#{case_id}`", inline=True)
    embed.add_field(name="Джерело", value=_source_label(source), inline=True)
    embed.add_field(name="Сервер", value=guild.name, inline=True)
    embed.add_field(name="Дія", value=action.upper(), inline=True)
    embed.add_field(name="Причина", value=reason[:1024], inline=False)

    if origin_text:
        embed.add_field(name="Звідки", value=origin_text[:1024], inline=False)

    if active_warns is not None:
        embed.add_field(name="Активних варнів", value=str(active_warns), inline=True)

    if duration_seconds:
        until = discord.utils.utcnow() + timedelta(seconds=duration_seconds)
        embed.add_field(
            name="Тривалість",
            value=f"{_format_duration(duration_seconds)} • до {discord.utils.format_dt(until, 'R')}",
            inline=False,
        )

    return embed


async def apply_case(
    bot: commands.Bot,
    guild: discord.Guild,
    user: discord.Member | discord.User,
    moderator: discord.Member | discord.User,
    action: str,
    reason: str,
    duration_seconds: int | None = None,
    source: str = "manual",
    origin_text: str | None = None,
) -> str:
    case_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc)
    duration_hours = (duration_seconds + 3599) // 3600 if duration_seconds else None

    await db.cases.insert_one(
        {
            "case_id": case_id,
            "guild_id": guild.id,
            "user_id": user.id,
            "moderator_id": moderator.id,
            "action": action,
            "reason": reason,
            "duration_seconds": duration_seconds,
            "duration_hours": duration_hours,
            "source": source,
            "origin_text": origin_text,
            "timestamp": now,
        }
    )

    if action == "warn":
        await db.guild_analytics.update_one(
            {"guild_id": guild.id, "date": now.strftime("%Y-%m-%d")},
            {"$inc": {"warns": 1}},
            upsert=True,
        )

    active_warns = await _count_active_warns(guild.id, user.id) if action == "warn" else None

    dm_embed = _build_dm_embed(
        guild=guild,
        moderator=moderator,
        action=action,
        reason=reason,
        case_id=case_id,
        source=source,
        duration_seconds=duration_seconds,
        origin_text=origin_text,
        active_warns=active_warns,
    )
    await _send_dm(user, dm_embed)

    if isinstance(user, discord.Member):
        try:
            if action == "mute":
                until = discord.utils.utcnow() + timedelta(seconds=duration_seconds or 86400)
                await user.timeout(until, reason=f"Case #{case_id}: {reason}")
            elif action == "kick":
                await user.kick(reason=f"Case #{case_id}: {reason}")
            elif action == "ban":
                await user.ban(reason=f"Case #{case_id}: {reason}", delete_message_days=0)
        except discord.Forbidden:
            pass

    log_embed = _build_log_embed(
        guild=guild,
        user=user,
        moderator=moderator,
        action=action,
        reason=reason,
        case_id=case_id,
        source=source,
        duration_seconds=duration_seconds,
        origin_text=origin_text,
        active_warns=active_warns,
    )
    await _send_case_log(guild, _log_key_for_source(source), log_embed)

    if action == "warn":
        rules = await _get_escalations(guild.id)
        for rule in sorted(rules, key=lambda x: x["count"]):
            if active_warns == rule["count"]:
                esc_action = rule.get("action", "mute")
                esc_dur = _parse_duration_to_seconds(str(rule.get("duration", "")).strip())
                await apply_case(
                    bot=bot,
                    guild=guild,
                    user=user,
                    moderator=bot.user,
                    action=esc_action,
                    reason=f"[Ескалація] Досягнуто {active_warns} попереджень. Case: #{case_id}",
                    duration_seconds=esc_dur if esc_action == "mute" else None,
                    source="escalation",
                    origin_text=f"Поріг ескалації: {active_warns} активних попереджень",
                )
                break

    return case_id
