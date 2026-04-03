"""
moderation.py
Сервісний шар для moderation cases: warn, mute, kick, ban, unban, ескалацій і логування.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord.ext import commands

from config.constants import Emojis
from modules.db import get_database
from services.metrics import inc_global_metric

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
    "unban": ("Розбанено на сервері", E_SHIELD, 0x1A1A2E),
}

ACTION_LABELS = {
    "warn": "попередження",
    "mute": "тайм-аут",
    "kick": "кік",
    "ban": "бан",
    "unban": "розбан",
}

ACTION_PERMISSIONS = {
    "mute": "moderate_members",
    "kick": "kick_members",
    "ban": "ban_members",
    "unban": "ban_members",
}


class ModerationActionError(RuntimeError):
    """Користувацька помилка moderation flow."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


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


def _normalize_timestamp(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _warn_case_state(case: dict[str, Any], decay_days: int, *, now: datetime | None = None) -> str:
    if case.get("revoked") is True:
        return "revoked"

    if decay_days <= 0:
        return "active"

    ts = _normalize_timestamp(case.get("timestamp"))
    if ts is None:
        return "active"

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=decay_days)
    return "decayed" if ts < cutoff else "active"


def build_active_warn_query(guild_id: int, user_id: int, decay_days: int, *, now: datetime | None = None) -> dict[str, Any]:
    query: dict[str, Any] = {
        "guild_id": guild_id,
        "user_id": user_id,
        "action": "warn",
        "revoked": {"$ne": True},
    }
    if decay_days > 0:
        now = now or datetime.now(timezone.utc)
        query["timestamp"] = {"$gte": now - timedelta(days=decay_days)}
    return query


def _get_bot_member(guild: discord.Guild) -> discord.Member | None:
    return guild.me or guild.get_member(guild._state.self_id)  # type: ignore[attr-defined]


def _member_like(entity: Any) -> bool:
    return hasattr(entity, "top_role") and hasattr(entity, "guild_permissions")


def validate_moderation_target(
    *,
    guild: discord.Guild,
    actor: Any | None,
    target: discord.Member | discord.User,
    action: str,
) -> str | None:
    action_label = ACTION_LABELS.get(action, "модерацію")
    target_is_member = isinstance(target, discord.Member) or _member_like(target)

    if getattr(target, "bot", False):
        return "Бота не можна модерувати цією командою."

    if actor is not None and getattr(actor, "id", None) == getattr(target, "id", None):
        return f"Не можна застосувати {action_label} до себе."

    if getattr(target, "id", None) == guild.owner_id:
        return "Не можна карати власника сервера."

    if actor is not None and _member_like(actor) and target_is_member:
        actor_is_owner = getattr(actor, "id", None) == guild.owner_id
        actor_top_role = getattr(actor, "top_role", None)
        target_top_role = getattr(target, "top_role", None)
        if not actor_is_owner and actor_top_role is not None and target_top_role is not None:
            if target_top_role >= actor_top_role:
                return "Ціль має рівну або вищу роль, ніж у модератора."

    bot_member = _get_bot_member(guild)
    if bot_member is None:
        return "Бот ще не готовий до модераційних дій у цьому сервері."

    if target_is_member and getattr(target, "id", None) != bot_member.id:
        target_top_role = getattr(target, "top_role", None)
        if target_top_role is not None and target_top_role >= bot_member.top_role:
            return "Бот не може модерувати ціль через рольову ієрархію."

    permission_name = ACTION_PERMISSIONS.get(action)
    if permission_name and not getattr(bot_member.guild_permissions, permission_name, False):
        return "Боту бракує прав для цієї модераційної дії."

    if action in {"mute", "kick", "ban"}:
        if not target_is_member:
            return "Для цієї дії ціль має бути учасником сервера."
        if target.id == bot_member.id:
            return "Бот не може модерувати самого себе."

    return None


async def _get_escalations(guild_id: int) -> list[dict]:
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    return settings.get("warn_escalation", [])


async def _count_active_warns(guild_id: int, user_id: int) -> int:
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    decay_days = settings.get("warn_decay_days", 0)
    return await db.cases.count_documents(build_active_warn_query(guild_id, user_id, decay_days))


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


async def _perform_discord_action(
    *,
    guild: discord.Guild,
    user: discord.Member | discord.User,
    action: str,
    case_id: str,
    reason: str,
    duration_seconds: int | None,
) -> None:
    if action == "warn":
        return
    try:
        if action == "mute":
            if not isinstance(user, discord.Member):
                raise ModerationActionError("Для цієї дії ціль має бути учасником сервера.")
            until = discord.utils.utcnow() + timedelta(seconds=duration_seconds or 86400)
            await user.timeout(until, reason=f"Case #{case_id}: {reason}")
        elif action == "kick":
            if not isinstance(user, discord.Member):
                raise ModerationActionError("Для цієї дії ціль має бути учасником сервера.")
            await user.kick(reason=f"Case #{case_id}: {reason}")
        elif action == "ban":
            if not isinstance(user, discord.Member):
                raise ModerationActionError("Для цієї дії ціль має бути учасником сервера.")
            await user.ban(reason=f"Case #{case_id}: {reason}", delete_message_days=0)
        elif action == "unban":
            await guild.unban(user, reason=f"Case #{case_id}: {reason}")
    except discord.Forbidden as exc:
        raise ModerationActionError("Discord відхилив дію. Перевір рольову ієрархію та права бота.") from exc
    except discord.HTTPException as exc:
        raise ModerationActionError("Discord не зміг виконати дію. Спробуй ще раз трохи пізніше.") from exc


async def _insert_case(
    *,
    guild: discord.Guild,
    user: discord.Member | discord.User,
    moderator: discord.Member | discord.User,
    action: str,
    reason: str,
    duration_seconds: int | None,
    source: str,
    origin_text: str | None,
    case_id: str,
    now: datetime,
) -> None:
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


async def _record_post_case_side_effects(
    *,
    bot: commands.Bot,
    guild: discord.Guild,
    user: discord.Member | discord.User,
    moderator: discord.Member | discord.User,
    action: str,
    reason: str,
    case_id: str,
    source: str,
    duration_seconds: int | None,
    origin_text: str | None,
) -> None:
    now = datetime.now(timezone.utc)
    active_warns = await _count_active_warns(guild.id, user.id) if action == "warn" else None

    if action == "warn":
        await db.guild_analytics.update_one(
            {"guild_id": guild.id, "date": now.strftime("%Y-%m-%d")},
            {"$inc": {"warns": 1}},
            upsert=True,
        )
        await inc_global_metric("warnings_issued_total")

    if source in {"auto", "escalation"}:
        await inc_global_metric("automod_actions_total")

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
                try:
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
                except ModerationActionError:
                    pass
                break


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
    if action != "unban":
        error = validate_moderation_target(
            guild=guild,
            actor=moderator if isinstance(moderator, discord.Member) else None,
            target=user,
            action=action,
        )
        if error:
            raise ModerationActionError(error)

    case_id = str(uuid.uuid4())[:8]
    await _perform_discord_action(
        guild=guild,
        user=user,
        action=action,
        case_id=case_id,
        reason=reason,
        duration_seconds=duration_seconds,
    )

    now = datetime.now(timezone.utc)
    await _insert_case(
        guild=guild,
        user=user,
        moderator=moderator,
        action=action,
        reason=reason,
        duration_seconds=duration_seconds,
        source=source,
        origin_text=origin_text,
        case_id=case_id,
        now=now,
    )
    await _record_post_case_side_effects(
        bot=bot,
        guild=guild,
        user=user,
        moderator=moderator,
        action=action,
        reason=reason,
        case_id=case_id,
        source=source,
        duration_seconds=duration_seconds,
        origin_text=origin_text,
    )
    return case_id


async def apply_unban_case(
    bot: commands.Bot,
    guild: discord.Guild,
    user: discord.User,
    moderator: discord.Member | discord.User,
    reason: str,
    source: str = "manual",
    origin_text: str | None = None,
) -> str:
    bot_member = _get_bot_member(guild)
    if bot_member is None:
        raise ModerationActionError("Бот ще не готовий до модераційних дій у цьому сервері.")
    if not getattr(bot_member.guild_permissions, "ban_members", False):
        raise ModerationActionError("Боту бракує прав `Ban Members`.")
    if moderator.id == user.id:
        raise ModerationActionError("Не можна розбанити себе цією командою.")

    return await apply_case(
        bot=bot,
        guild=guild,
        user=user,
        moderator=moderator,
        action="unban",
        reason=reason,
        source=source,
        origin_text=origin_text,
    )
