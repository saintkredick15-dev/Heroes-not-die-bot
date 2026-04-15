from __future__ import annotations

import random
import time
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from pymongo import UpdateOne

from config.constants import Emojis
from modules.db import get_database, get_guild_settings, get_user_data, invalidate_user_data
from repositories.user import get_level_xp, get_user, update_user
from services.metrics import mark_user_active
from services.stats_contract import analytics_day_key
from utils.activity_config import DEFAULT_ACTIVITY, get_activity_config, sync_member_reward_roles
from utils.eco_helpers import add_daily_earnings_inc
from utils.ui_contract import surface_embed

db = get_database()

DEFAULT_MESSAGE_XP = DEFAULT_ACTIVITY["message_xp"]
DEFAULT_REACTION_XP = DEFAULT_ACTIVITY["reaction_xp"]
DEFAULT_VOICE_XP_PER_MINUTE = DEFAULT_ACTIVITY["voice_xp_per_minute"]

E_NOTIFICATION = Emojis.NOTIFICATION.value
E_NOTIFICATION_OFF = Emojis.NOTIFICATION_OFF.value
E_CROSS = Emojis.CROSS.value
E_CELEBRATION = Emojis.CELEBRATION.value


class LevelUpView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, notify_enabled: bool):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.toggle_notify.label = "Вимкнути сповіщення" if notify_enabled else "Увімкнути сповіщення"
        self.toggle_notify.emoji = discord.PartialEmoji.from_str(
            E_NOTIFICATION_OFF if notify_enabled else E_NOTIFICATION
        )

    @discord.ui.button(
        label="Вимкнути сповіщення",
        emoji=discord.PartialEmoji.from_str(E_NOTIFICATION_OFF),
        style=discord.ButtonStyle.secondary,
        custom_id="levelup_toggle_notify",
    )
    async def toggle_notify(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(f"{E_CROSS} Це не твоє сповіщення.", ephemeral=True)
            return

        doc = await get_user_data(db, self.guild_id, self.user_id) or {}
        current = bool(doc.get("levelup_notify", True))
        new_value = not current

        await db.users.update_one(
            {"guild_id": self.guild_id, "user_id": self.user_id},
            {"$set": {"levelup_notify": new_value}},
            upsert=True,
        )
        await invalidate_user_data(self.guild_id, self.user_id)

        button.label = "Вимкнути сповіщення" if new_value else "Увімкнути сповіщення"
        button.emoji = discord.PartialEmoji.from_str(E_NOTIFICATION_OFF if new_value else E_NOTIFICATION)
        await interaction.response.edit_message(view=self)


def _get_levelup_channel(guild: discord.Guild, activity_config: dict) -> discord.TextChannel | None:
    channel_id = activity_config.get("levelup_channel_id")
    if not channel_id:
        return None
    channel = guild.get_channel(channel_id)
    return channel if isinstance(channel, discord.TextChannel) else None


async def _send_level_up(
    channel: discord.TextChannel,
    member: discord.Member,
    new_level: int,
    activity_config: dict,
    user_data: dict,
) -> None:
    ping_enabled = activity_config.get("levelup_ping_user", True)
    opt_out_enabled = activity_config.get("levelup_allow_opt_out", True)
    should_ping = ping_enabled and (not opt_out_enabled or user_data.get("levelup_notify", True))
    mention = member.mention if should_ping else f"**{member.display_name}**"

    embed = surface_embed(
        "gameplay",
        title=f"{E_CELEBRATION} Новий рівень",
        description=f"{mention} досягнув **{new_level} рівня**.",
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    view = None
    if ping_enabled and opt_out_enabled:
        view = LevelUpView(member.guild.id, member.id, user_data.get("levelup_notify", True))

    try:
        await channel.send(embed=embed, view=view)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def _level_up_check(
    guild: discord.Guild,
    member: discord.Member,
    user_data: dict,
    activity_config: dict,
) -> None:
    current_level = user_data.get("level", 1)
    current_xp = user_data.get("xp", 0)
    new_level = current_level

    while current_xp >= get_level_xp(new_level):
        current_xp -= get_level_xp(new_level)
        new_level += 1

    if new_level == current_level:
        return

    updated_data = {**user_data, "xp": current_xp, "level": new_level}
    await update_user(db, guild.id, member, member.id, {"xp": current_xp, "level": new_level})
    await sync_member_reward_roles(member, new_level, activity_config)

    notify_channel = _get_levelup_channel(guild, activity_config)
    if notify_channel:
        await _send_level_up(notify_channel, member, new_level, activity_config, updated_data)


class ActivityEvents(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_voice_time.start()
        self._msg_cooldowns: dict[int, dict[int, float]] = {}
        self._react_cooldowns: dict[int, dict[int, float]] = {}

    def cog_unload(self):
        self.update_voice_time.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id or not message.guild:
            return

        settings = await get_guild_settings(db, message.guild.id)
        eco = settings.get("economy", {}) if isinstance(settings.get("economy"), dict) else {}
        activity = get_activity_config(settings)
        user_data = await get_user(db, message.guild.id, message.author.id)

        message_xp = int(activity.get("message_xp", DEFAULT_MESSAGE_XP))
        today = datetime.now().strftime("%Y-%m-%d")
        history = dict(user_data.get("history", {}))
        history[today] = history.get(today, 0) + message_xp

        update_data = {
            "xp": user_data["xp"] + message_xp,
            "messages": user_data["messages"] + 1,
            "history": history,
            "last_active_at": datetime.now(timezone.utc),
        }

        if eco.get("enabled", True):
            guild_cooldowns = self._msg_cooldowns.setdefault(message.guild.id, {})
            now = time.time()
            if now - guild_cooldowns.get(message.author.id, 0) >= eco.get("msg_cooldown", 60):
                guild_cooldowns[message.author.id] = now
                earn_conf = eco.get("msg_earn", [5, 10])
                if isinstance(earn_conf, list) and len(earn_conf) == 2:
                    earned = random.randint(earn_conf[0], earn_conf[1])
                else:
                    earned = int(earn_conf) if isinstance(earn_conf, (int, float, str)) else 5
                update_data["wallet"] = user_data.get("wallet", 0) + earned
                update_data["total_earned"] = user_data.get("total_earned", 0) + earned

        user_data.update(update_data)
        inc_data = {
            "xp_week": message_xp,
            "xp_month": message_xp,
            "messages_week": 1,
            "messages_month": 1,
        }
        if "wallet" in update_data:
            inc_data["week_earned"] = earned
            inc_data["month_earned"] = earned
            add_daily_earnings_inc(inc_data, earned)

        await db.users.update_one(
            {"guild_id": message.guild.id, "user_id": message.author.id},
            {"$set": update_data, "$inc": inc_data},
            upsert=True,
        )
        await invalidate_user_data(message.guild.id, message.author.id)
        await mark_user_active(message.guild.id, message.author.id)
        await _level_up_check(message.guild, message.author, user_data, activity)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member):
        if user.bot or not reaction.message.guild:
            return

        settings = await get_guild_settings(db, reaction.message.guild.id)
        eco = settings.get("economy", {}) if isinstance(settings.get("economy"), dict) else {}
        activity = get_activity_config(settings)
        user_data = await get_user(db, reaction.message.guild.id, user.id)

        reaction_xp = int(activity.get("reaction_xp", DEFAULT_REACTION_XP))
        today = datetime.now().strftime("%Y-%m-%d")
        history = dict(user_data.get("history", {}))
        history[today] = history.get(today, 0) + reaction_xp

        update_data = {
            "xp": user_data["xp"] + reaction_xp,
            "reactions": user_data["reactions"] + 1,
            "history": history,
            "last_active_at": datetime.now(timezone.utc),
        }

        if eco.get("enabled", True):
            guild_cooldowns = self._react_cooldowns.setdefault(reaction.message.guild.id, {})
            now = time.time()
            if now - guild_cooldowns.get(user.id, 0) >= eco.get("reaction_cooldown", 30):
                guild_cooldowns[user.id] = now
                earned = eco.get("reaction_earn", 2)
                update_data["wallet"] = user_data.get("wallet", 0) + earned
                update_data["total_earned"] = user_data.get("total_earned", 0) + earned

        user_data.update(update_data)
        inc_data = {
            "xp_week": reaction_xp,
            "xp_month": reaction_xp,
            "reactions_week": 1,
            "reactions_month": 1,
        }
        if "wallet" in update_data:
            inc_data["week_earned"] = earned
            inc_data["month_earned"] = earned
            add_daily_earnings_inc(inc_data, earned)

        await db.users.update_one(
            {"guild_id": reaction.message.guild.id, "user_id": user.id},
            {"$set": update_data, "$inc": inc_data},
            upsert=True,
        )
        await invalidate_user_data(reaction.message.guild.id, user.id)
        await mark_user_active(reaction.message.guild.id, user.id)
        await _level_up_check(reaction.message.guild, user, user_data, activity)

    @tasks.loop(minutes=1)
    async def update_voice_time(self):
        today = datetime.now().strftime("%Y-%m-%d")

        for guild in self.bot.guilds:
            members_to_process: list[discord.Member] = []
            for voice_channel in guild.voice_channels:
                for member in voice_channel.members:
                    if not member.bot:
                        members_to_process.append(member)

            if not members_to_process:
                continue

            member_ids = [member.id for member in members_to_process]
            existing_docs = {
                doc["user_id"]: doc
                async for doc in db.users.find({"guild_id": guild.id, "user_id": {"$in": member_ids}})
            }

            settings = await get_guild_settings(db, guild.id)
            eco = settings.get("economy", {}) if isinstance(settings.get("economy"), dict) else {}
            activity = get_activity_config(settings)
            eco_enabled = eco.get("enabled", True)
            voice_earn = eco.get("voice_earn", 3)
            voice_xp = int(activity.get("voice_xp_per_minute", DEFAULT_VOICE_XP_PER_MINUTE))

            operations = []
            for member in members_to_process:
                user_data = existing_docs.get(member.id) or await get_user(db, guild.id, member.id)
                history = dict(user_data.get("history", {}))
                history[today] = history.get(today, 0) + voice_xp

                inc_query = {
                    "xp": voice_xp,
                    "voice_minutes": 1,
                    "voice_minutes_week": 1,
                    "voice_minutes_month": 1,
                    "xp_week": voice_xp,
                    "xp_month": voice_xp,
                }
                if eco_enabled:
                    inc_query["wallet"] = voice_earn
                    inc_query["total_earned"] = voice_earn
                    inc_query["week_earned"] = voice_earn
                    inc_query["month_earned"] = voice_earn
                    add_daily_earnings_inc(inc_query, voice_earn)

                operations.append(
                    UpdateOne(
                        {"guild_id": guild.id, "user_id": member.id},
                        {
                            "$inc": inc_query,
                            "$set": {
                                "history": history,
                                "username": member.display_name,
                                "last_active_at": datetime.now(timezone.utc),
                                "avatar": member.display_avatar.url if member.display_avatar else None,
                            },
                        },
                    )
                )

            if operations:
                await db.users.bulk_write(operations, ordered=False)
                for member in members_to_process:
                    await invalidate_user_data(guild.id, member.id)
                await db.guild_analytics.update_one(
                    {"guild_id": guild.id, "date": analytics_day_key()},
                    {"$inc": {"voice_minutes": len(members_to_process)}},
                    upsert=True,
                )

            updated_docs = {
                doc["user_id"]: doc
                async for doc in db.users.find({"guild_id": guild.id, "user_id": {"$in": member_ids}})
            }

            for member in members_to_process:
                user_data = updated_docs.get(member.id)
                if user_data:
                    await _level_up_check(guild, member, user_data, activity)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityEvents(bot))
