"""
analytics.py — Фонова аналітика сервера.

Збирає агреговану статистику у колекцію `guild_analytics` (один документ на день).
Раз на N днів публікує автоматичний звіт у вказаний канал.
"""
from __future__ import annotations

import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
from modules.db import get_database

db = get_database()
_col_settings = db.guild_settings
_col_analytics = db.guild_analytics

# ── Emoji ────────────────────────────────────────────────────────────────────
E_CHAT    = "<:chat:1475953787687403716>"
E_MICRO   = "<:micro:1475954046350135346>"
E_MEMBERS = "<:autorole:1476198471307624530>"
E_COINS   = "<:coins:1477376020318388274>"
E_WARN    = "<:warn:1477376152191373504>"
E_MUTE    = "<:mutemicro:1476200127063396443>"
E_BAN     = "<:ban:1476199074494681170>"
E_STATS   = "<:statistics:1477721796857041067>"
E_HAMMER  = "<:hammer:1477376411642761479>"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _inc_analytics(guild_id: int, fields: dict) -> None:
    """Атомарний $inc одного або кількох лічильників за поточний день."""
    await _col_analytics.update_one(
        {"guild_id": guild_id, "date": _today()},
        {"$inc": fields},
        upsert=True,
    )


async def _get_settings(guild_id: int) -> dict:
    return await _col_settings.find_one({"_id": guild_id}) or {}


async def _build_stats_embed(guild: discord.Guild, days: int) -> discord.Embed:
    """Збирає та повертає сумарний Embed за останні `days` днів."""
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    pipeline = [
        {"$match": {"guild_id": guild.id, "date": {"$gte": cutoff_date}}},
        {
            "$group": {
                "_id": None,
                "messages":      {"$sum": "$messages"},
                "voice_minutes": {"$sum": "$voice_minutes"},
                "joins":         {"$sum": "$joins"},
                "leaves":        {"$sum": "$leaves"},
                "warns":         {"$sum": "$warns"},
                "mutes":         {"$sum": "$mutes"},
                "bans":          {"$sum": "$bans"},
                "economy":       {"$sum": "$economy_given"},
            }
        },
    ]

    result = {}
    async for doc in _col_analytics.aggregate(pipeline):
        result = doc

    voice_hours = round(result.get("voice_minutes", 0) / 60, 1)
    net_members = result.get("joins", 0) - result.get("leaves", 0)

    embed = discord.Embed(
        title=f"{E_STATS} Статистика сервера за {days} днів",
        color=0x1a1a2e,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

    embed.add_field(
        name=f"{E_CHAT}  Активність у чаті",
        value=f"```{result.get('messages', 0):,} повідомлень```",
        inline=True,
    )
    embed.add_field(
        name=f"{E_MICRO}  Голосова активність",
        value=f"```{voice_hours:,} годин```",
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(
        name=f"{E_MEMBERS}  Учасники",
        value=(
            f"```+{result.get('joins', 0)} прийшло\n"
            f"-{result.get('leaves', 0)} пішло\n"
            f"{'≈' if net_members >= 0 else ''}{net_members:+d} нетто```"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"{E_COINS}  Економіка",
        value=f"```{result.get('economy', 0):,} монет нараховано```",
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(
        name=f"{E_HAMMER}  Модераційні дії",
        value=(
            f"{E_WARN} Попереджень: **{result.get('warns', 0)}**\n"
            f"{E_MUTE} Мутів: **{result.get('mutes', 0)}**\n"
            f"{E_BAN}  Банів: **{result.get('bans', 0)}**"
        ),
        inline=False,
    )
    embed.set_footer(text="Vangard Analytics")
    return embed


# ── Cog ──────────────────────────────────────────────────────────────────────

class AnalyticsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_stats_publish.start()

    def cog_unload(self):
        self.check_stats_publish.cancel()

    # ── Лічильники повідомлень ──────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id or not message.guild:
            return
        await _inc_analytics(message.guild.id, {"messages": 1})

    # ── Лічильники реакцій ─────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member):
        if user.bot or not reaction.message.guild:
            return
        await _inc_analytics(reaction.message.guild.id, {"reactions": 1})

    # ── Приєднання / вихід ─────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await _inc_analytics(member.guild.id, {"joins": 1})

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await _inc_analytics(member.guild.id, {"leaves": 1})

    # ── Голосова активність (хвилини збираються в activity.py) ────────────
    # Дублювати тут не треба, але якщо захочемо відокремити — можна додати
    # окремий tasks.loop тут.

    # ── Авто-публікація статистики ─────────────────────────────────────────
    @tasks.loop(hours=1)
    async def check_stats_publish(self):
        """Раз на годину перевіряємо, чи настав час публікувати стату."""
        now = datetime.now(timezone.utc)

        async for settings in _col_settings.find(
            {"stats_channel": {"$exists": True, "$ne": None}}
        ):
            guild_id = settings["_id"]
            channel_id = settings.get("stats_channel")
            interval_days = max(1, min(30, settings.get("stats_interval_days", 7)))
            last_post_ts = settings.get("stats_last_post")

            if last_post_ts is not None:
                last_post = datetime.fromtimestamp(last_post_ts, tz=timezone.utc)
                if (now - last_post).days < interval_days:
                    continue
            else:
                # Перший запуск — ставимо мітку і чекаємо повний інтервал
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
