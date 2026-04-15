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
from services.stats_contract import aggregate_guild_analytics, aggregate_guild_analytics_lifetime, analytics_day_key
from utils.eco_helpers import sum_recent_daily_earnings

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
E_TICKET = Emojis.TICKET.value

async def _inc_analytics(guild_id: int, fields: dict[str, int]) -> None:
    await _col_analytics.update_one(
        {"guild_id": guild_id, "date": analytics_day_key()},
        {"$inc": fields},
        upsert=True,
    )


async def _sum_period_economy(guild_id: int, days: int) -> int:
    total = 0
    async for doc in db.users.find({"guild_id": guild_id}, {"economy_daily_earnings": 1}):
        total += sum_recent_daily_earnings(doc, days)
    return total


def _timeout_is_active(member: discord.Member) -> bool:
    until = member.timed_out_until
    return until is not None and until > discord.utils.utcnow()


def _summary_line(
    *,
    messages: int,
    voice_hours: float,
    mod_actions_total: int,
    economy: int,
    tickets_opened: int,
    tickets_closed: int,
) -> str:
    summary_bits = [f"Чат: **{messages:,}**", f"Войс: **{voice_hours:.1f} год**"]
    summary_bits.append(f"Модерація: **{mod_actions_total}**")
    summary_bits.append(f"Економіка: **{economy:,}**")
    summary_bits.append(f"Тікети: **{tickets_opened}/{tickets_closed}**")
    return " • ".join(summary_bits)


async def _build_stats_embed(guild: discord.Guild, days: int) -> discord.Embed:
    now = datetime.now(timezone.utc)
    result = await aggregate_guild_analytics(guild.id, days, collection=_col_analytics)
    lifetime = await aggregate_guild_analytics_lifetime(guild.id, collection=_col_analytics)

    messages = result["messages"]
    reactions = result["reactions"]
    voice_hours = round(result["voice_minutes"] / 60, 1)
    joins = result["joins"]
    leaves = result["leaves"]
    net_members = result["net_members"]
    tickets_opened = result["tickets_opened"]
    tickets_closed = result["tickets_closed"]
    warns = result["warns"]
    mutes = result["mutes"]
    bans = result["bans"]
    unbans = result["unbans"]
    mod_actions_total = result["mod_actions_total"]
    economy = await _sum_period_economy(guild.id, days)
    hypothetical_members = max(0, guild.member_count + lifetime["leaves"])
    period_start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    next_report = now + timedelta(days=days)

    embed = discord.Embed(
        title=f"{E_STATS} Статистика сервера за {days} днів",
        description=_summary_line(
            messages=messages,
            voice_hours=voice_hours,
            mod_actions_total=mod_actions_total,
            economy=economy,
            tickets_opened=tickets_opened,
            tickets_closed=tickets_closed,
        ),
        color=0x1A1A2E,
        timestamp=now,
    )
    embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
    embed.add_field(
        name="Період",
        value=f"<t:{int(period_start.timestamp())}:d> — <t:{int(now.timestamp())}:d>",
        inline=False,
    )
    embed.add_field(
        name="Наступний звіт",
        value=f"<t:{int(next_report.timestamp())}:f> • <t:{int(next_report.timestamp())}:R>",
        inline=False,
    )

    embed.add_field(
        name=f"{E_CHAT} Активність",
        value=(
            f"Повідомлень: **{messages:,}**\n"
            f"Реакцій: **{reactions:,}**\n"
            f"Голосом: **{voice_hours:.1f} год**"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{E_MEMBERS} Учасники",
        value=(
            f"Прийшло: **{joins}**\n"
            f"Пішло: **{leaves}**\n"
            f"Нетто: **{net_members:+d}**\n"
            f"Якби ніхто не пішов: **{hypothetical_members:,}**"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{E_COINS} Економіка",
        value=(
            f"Нараховано: **{economy:,}**\n"
            f"Періодичний snapshot без reset-ів"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{E_HAMMER} Модерація",
        value=(
            f"{E_WARN} Попереджень: **{warns}**\n"
            f"{E_MUTE} Тайм-аутів: **{mutes}**\n"
            f"{E_BAN} Банів: **{bans}**\n"
            f"Розбанів: **{unbans}**\n"
            f"Всього дій: **{mod_actions_total}**"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{E_TICKET} Tickets",
        value=(
            f"Відкрито: **{tickets_opened}**\n"
            f"Закрито: **{tickets_closed}**"
        ),
        inline=True,
    )
    embed.set_footer(text="Автоматичний періодичний snapshot сервера")
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
