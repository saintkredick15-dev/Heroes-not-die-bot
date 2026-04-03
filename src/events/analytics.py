"""
analytics.py — фонова аналітика сервера.

Збирає агреговану статистику у колекцію `guild_analytics` і раз на N днів
публікує короткий звіт у вказаний канал.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from config.constants import Emojis
from modules.db import get_database

db = get_database()
_col_settings = db.guild_settings
_col_analytics = db.guild_analytics

E_CHAT = Emojis.CHAT.value
E_MICRO = Emojis.MICRO.value
E_MEMBERS = Emojis.AUTOROLE.value
E_COINS = Emojis.COINS_ALT.value
E_WARN = Emojis.WARN.value
E_MUTE = Emojis.MUTE.value
E_BAN = Emojis.BAN.value
E_STATS = Emojis.STATS.value
E_HAMMER = Emojis.HAMMER.value


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _inc_analytics(guild_id: int, fields: dict[str, int]) -> None:
    await _col_analytics.update_one(
        {"guild_id": guild_id, "date": _today()},
        {"$inc": fields},
        upsert=True,
    )


def _timeout_is_active(member: discord.Member) -> bool:
    until = member.timed_out_until
    return until is not None and until > discord.utils.utcnow()


def _summary_line(*, messages: int, voice_hours: float, net_members: int, warns: int, mutes: int, bans: int) -> str:
    summary_bits = [f"Чат: **{messages:,}**", f"Войс: **{voice_hours:.1f} год**"]
    if net_members:
        direction = "зріс" if net_members > 0 else "просів"
        summary_bits.append(f"Сервер {direction} на **{net_members:+d}**")
    mod_total = warns + mutes + bans
    if mod_total:
        summary_bits.append(f"Модерація: **{mod_total}** дій")
    return " • ".join(summary_bits)


async def _build_stats_embed(guild: discord.Guild, days: int) -> discord.Embed:
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    pipeline = [
        {"$match": {"guild_id": guild.id, "date": {"$gte": cutoff_date}}},
        {
            "$group": {
                "_id": None,
                "messages": {"$sum": "$messages"},
                "voice_minutes": {"$sum": "$voice_minutes"},
                "joins": {"$sum": "$joins"},
                "leaves": {"$sum": "$leaves"},
                "warns": {"$sum": "$warns"},
                "mutes": {"$sum": "$mutes"},
                "bans": {"$sum": "$bans"},
                "unbans": {"$sum": "$unbans"},
                "economy": {"$sum": "$economy_given"},
            }
        },
    ]

    result: dict[str, int] = {}
    async for doc in _col_analytics.aggregate(pipeline):
        result = doc

    messages = result.get("messages", 0)
    voice_hours = round(result.get("voice_minutes", 0) / 60, 1)
    joins = result.get("joins", 0)
    leaves = result.get("leaves", 0)
    net_members = joins - leaves
    warns = result.get("warns", 0)
    mutes = result.get("mutes", 0)
    bans = result.get("bans", 0)
    unbans = result.get("unbans", 0)
    economy = result.get("economy", 0)

    embed = discord.Embed(
        title=f"{E_STATS} Статистика сервера за {days} днів",
        description=_summary_line(
            messages=messages,
            voice_hours=voice_hours,
            net_members=net_members,
            warns=warns,
            mutes=mutes,
            bans=bans,
        ),
        color=0x1A1A2E,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

    embed.add_field(
        name=f"{E_CHAT} Активність",
        value=(
            f"Повідомлень: **{messages:,}**\n"
            f"Голосом: **{voice_hours:.1f} год**"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{E_MEMBERS} Учасники",
        value=(
            f"Прийшло: **{joins}**\n"
            f"Пішло: **{leaves}**\n"
            f"Нетто: **{net_members:+d}**"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{E_COINS} Економіка",
        value=f"Нараховано: **{economy:,}**",
        inline=True,
    )
    embed.add_field(
        name=f"{E_HAMMER} Модерація",
        value=(
            f"{E_WARN} Попереджень: **{warns}**\n"
            f"{E_MUTE} Тайм-аутів: **{mutes}**\n"
            f"{E_BAN} Банів: **{bans}**"
            + (f"\nРозбанів: **{unbans}**" if unbans else "")
        ),
        inline=False,
    )
    embed.set_footer(text="Автоматичний звіт сервера")
    return embed


class AnalyticsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_stats_publish.start()

    def cog_unload(self):
        self.check_stats_publish.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id or not message.guild:
            return
        await _inc_analytics(message.guild.id, {"messages": 1})

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member):
        if user.bot or not reaction.message.guild:
            return
        await _inc_analytics(reaction.message.guild.id, {"reactions": 1})

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await _inc_analytics(member.guild.id, {"joins": 1})

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await _inc_analytics(member.guild.id, {"leaves": 1})

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await _inc_analytics(guild.id, {"bans": 1})

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        await _inc_analytics(guild.id, {"unbans": 1})

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.guild.id != after.guild.id or after.bot:
            return
        if _timeout_is_active(after) and not _timeout_is_active(before):
            await _inc_analytics(after.guild.id, {"mutes": 1})

    @tasks.loop(hours=1)
    async def check_stats_publish(self):
        now = datetime.now(timezone.utc)

        async for settings in _col_settings.find({"stats_channel": {"$exists": True, "$ne": None}}):
            guild_id = settings["_id"]
            channel_id = settings.get("stats_channel")
            interval_days = max(1, min(30, settings.get("stats_interval_days", 7)))
            last_post_ts = settings.get("stats_last_post")

            if last_post_ts is not None:
                last_post = datetime.fromtimestamp(last_post_ts, tz=timezone.utc)
                if (now - last_post).days < interval_days:
                    continue
            else:
                await _col_settings.update_one(
                    {"_id": guild_id},
                    {"$set": {"stats_last_post": now.timestamp()}},
                )
                continue

            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                embed = await _build_stats_embed(guild, interval_days)
                await channel.send(embed=embed)
                await _col_settings.update_one(
                    {"_id": guild_id},
                    {"$set": {"stats_last_post": now.timestamp()}},
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    @check_stats_publish.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(AnalyticsCog(bot))
