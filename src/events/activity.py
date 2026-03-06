import discord
from discord.ext import commands, tasks
from datetime import datetime
import time
import random
from pymongo import UpdateOne
from modules.db import get_database
from repositories.user import get_user, update_user, get_level_xp

db = get_database()

# ── Кастомний emoji для кнопки "вимкнути сповіщення" ────────────────────────
E_OFFNOTIF = "<:offnotification:1476242115536097402>"

EMBED_COLOR = 0x1a1a2e


# ── Level-up UI ───────────────────────────────────────────────────────────────

class LevelUpView(discord.ui.View):
    """Кнопка toggle сповіщень під level-up embed."""

    def __init__(self, user_id: int, notify: bool):
        super().__init__(timeout=None)  # живе поки бот запущений
        self.user_id = user_id
        # Початковий стан кнопки відповідає поточному налаштуванню
        btn = self.toggle_notify
        if notify:
            btn.label = "Вимкнути сповіщення"
            btn.emoji = discord.PartialEmoji.from_str("<:offnotification:1476242115536097402>")
        else:
            btn.label = "Ввімкнути сповіщення"
            btn.emoji = discord.PartialEmoji.from_str("<:notification:1476256523519787161>")

    @discord.ui.button(
        label="Вимкнути сповіщення",
        emoji=discord.PartialEmoji.from_str("<:offnotification:1476242115536097402>"),
        style=discord.ButtonStyle.secondary,
        custom_id="levelup_toggle_notify",
    )
    async def toggle_notify(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Тільки той юзер якому адресоване сповіщення
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Це не твоє сповіщення.", ephemeral=True
            )
            return

        # Читаємо поточний стан з DB і перемикаємо
        doc = await db.users.find_one(
            {"guild_id": interaction.guild.id, "user_id": self.user_id}
        )
        current = (doc or {}).get("levelup_notify", True)
        new_val = not current

        await db.users.update_one(
            {"guild_id": interaction.guild.id, "user_id": self.user_id},
            {"$set": {"levelup_notify": new_val}},
        )

        if new_val:
            button.label = "Вимкнути сповіщення"
            button.emoji = discord.PartialEmoji.from_str("<:offnotification:1476242115536097402>")
        else:
            button.label = "Ввімкнути сповіщення"
            button.emoji = discord.PartialEmoji.from_str("<:notification:1476256523519787161>")

        await interaction.response.edit_message(view=self)


async def get_levelup_channel(guild: discord.Guild) -> discord.TextChannel | None:
    """
    Повертає канал для level-up сповіщень.
    Читаємо з guild_settings (налаштовано через /panel).
    Якщо не налаштовано — None.
    """
    settings = await db.guild_settings.find_one({"_id": guild.id}) or {}
    channel_id = settings.get("levelup_channel_id")
    if not channel_id:
        return None
    channel = guild.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


async def send_level_up(
    channel: discord.TextChannel,
    member: discord.Member,
    new_level: int,
    notify: bool,
) -> None:
    """
    Відправляє level-up embed.
    notify=True  → з @mention (тег юзера)
    notify=False → без тегу (тихе сповіщення), кнопка пропонує ввімкнути
    """
    name_str = member.mention if notify else f"**{member.display_name}**"
    embed = discord.Embed(
        description=f"## 🎉 Level Up!\n{name_str} підвищився до **рівня {new_level}**!",
        color=EMBED_COLOR,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    view = LevelUpView(member.id, notify=notify)
    try:
        await channel.send(embed=embed, view=view)
    except (discord.Forbidden, discord.HTTPException):
        pass



# ── Level-up check ────────────────────────────────────────────────────────────

async def level_up_check(
    message: discord.Message,
    user_data: dict,
) -> None:
    """Перевіряємо і застосовуємо level-up після on_message."""
    leveled_up = False
    new_level = user_data["level"]
    cur_xp = user_data["xp"]

    while cur_xp >= get_level_xp(new_level):
        cur_xp -= get_level_xp(new_level)
        new_level += 1
        leveled_up = True

    if leveled_up:
        await update_user(
            db,
            message.guild.id,
            message.author,
            message.author.id,
            {"xp": cur_xp, "level": new_level},
        )
        notify_ch = await get_levelup_channel(message.guild)
        if notify_ch:
            notify = user_data.get("levelup_notify", True)
            await send_level_up(notify_ch, message.author, new_level, notify=notify)


# ── Cog ───────────────────────────────────────────────────────────────────────

class ActivityEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_voice_time.start()
        # Economy cooldown caches
        self._msg_cooldowns: dict[int, dict[int, float]] = {}
        self._react_cooldowns: dict[int, dict[int, float]] = {}

    def cog_unload(self):
        self.update_voice_time.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id or not message.guild:
            return

        user_data = await get_user(db, message.guild.id, message.author.id)

        today = datetime.now().strftime("%Y-%m-%d")
        history = user_data.get("history", {})
        history[today] = history.get(today, 0) + 10

        update_data = {
            "xp": user_data["xp"] + 10,
            "messages": user_data["messages"] + 1,
            "history": history,
        }

        # --- Економіка: Валюта за повідомлення ---
        settings = await db.guild_settings.find_one({"_id": message.guild.id}) or {}
        eco = settings.get("economy", {})
        if eco.get("enabled", True):
            guild_cds = self._msg_cooldowns.setdefault(message.guild.id, {})
            now = time.time()
            if now - guild_cds.get(message.author.id, 0) >= eco.get("msg_cooldown", 60):
                guild_cds[message.author.id] = now
                earn_conf = eco.get("msg_earn", [5, 10])
                if isinstance(earn_conf, list) and len(earn_conf) == 2:
                    earned = random.randint(earn_conf[0], earn_conf[1])
                else:
                    earned = int(earn_conf) if isinstance(earn_conf, (int, float, str)) else 5
                update_data["wallet"] = user_data.get("wallet", 0) + earned
                update_data["total_earned"] = user_data.get("total_earned", 0) + earned
        # ----------------------------------------

        user_data.update(update_data)
        # Also increment xp leaderboard weekly/monthly counters
        await db.users.update_one(
            {"guild_id": message.guild.id, "user_id": message.author.id},
            {"$set": update_data, "$inc": {"xp_week": 10, "xp_month": 10}},
            upsert=True
        )
        await level_up_check(message, user_data)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member):
        if user.bot or not reaction.message.guild:
            return

        user_data = await get_user(db, reaction.message.guild.id, user.id)

        today = datetime.now().strftime("%Y-%m-%d")
        history = user_data.get("history", {})
        history[today] = history.get(today, 0) + 2

        update_data = {
            "xp": user_data["xp"] + 2,
            "reactions": user_data["reactions"] + 1,
            "history": history,
        }

        # --- Економіка: Валюта за реакції ---
        settings = await db.guild_settings.find_one({"_id": reaction.message.guild.id}) or {}
        eco = settings.get("economy", {})
        if eco.get("enabled", True):
            guild_cds = self._react_cooldowns.setdefault(reaction.message.guild.id, {})
            now = time.time()
            if now - guild_cds.get(user.id, 0) >= eco.get("reaction_cooldown", 30):
                guild_cds[user.id] = now
                earned = eco.get("reaction_earn", 2)
                update_data["wallet"] = user_data.get("wallet", 0) + earned
                update_data["total_earned"] = user_data.get("total_earned", 0) + earned
        # ------------------------------------

        await db.users.update_one(
            {"guild_id": reaction.message.guild.id, "user_id": user.id},
            {"$set": update_data, "$inc": {"xp_week": 2, "xp_month": 2}},
            upsert=True
        )

    @tasks.loop(minutes=1)
    async def update_voice_time(self):
        """
        Bulk-write для войс XP.
        Після bulk_write — перевіряємо level-up для кожного юзера.
        """
        today = datetime.now().strftime("%Y-%m-%d")

        for guild in self.bot.guilds:
            operations = []
            members_to_process: list[discord.Member] = []

            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot:
                        continue
                    members_to_process.append(member)

            if not members_to_process:
                continue

            # Завантажуємо всіх одним запитом
            member_ids = [m.id for m in members_to_process]
            existing_docs: dict[int, dict] = {
                doc["user_id"]: doc
                async for doc in db.users.find(
                    {"guild_id": guild.id, "user_id": {"$in": member_ids}}
                )
            }

            # Завантажуємо settings для гільдії
            settings = await db.guild_settings.find_one({"_id": guild.id}) or {}
            eco = settings.get("economy", {})
            eco_enabled = eco.get("enabled", True)
            voice_earn = eco.get("voice_earn", 3)

            for member in members_to_process:
                user_data = existing_docs.get(member.id)
                if not user_data:
                    user_data = await get_user(db, guild.id, member.id)

                history = dict(user_data.get("history", {}))
                history[today] = history.get(today, 0) + 5

                inc_query = {"xp": 5, "voice_minutes": 1, "xp_week": 5, "xp_month": 5}
                if eco_enabled:
                    inc_query["wallet"] = voice_earn
                    inc_query["total_earned"] = voice_earn

                operations.append(
                    UpdateOne(
                        {"guild_id": guild.id, "user_id": member.id},
                        {
                            "$inc": inc_query,
                            "$set": {
                                "history": history,
                                "username": member.display_name,
                                "avatar": (
                                    member.display_avatar.url
                                    if member.display_avatar
                                    else None
                                ),
                            },
                        },
                    )
                )

            if operations:
                await db.users.bulk_write(operations, ordered=False)

            # ── Level-up check після bulk_write ─────────────────────────────
            # Перечитуємо оновлені дані з БД (один запит на гільдію)
            updated_docs: dict[int, dict] = {
                doc["user_id"]: doc
                async for doc in db.users.find(
                    {"guild_id": guild.id, "user_id": {"$in": member_ids}}
                )
            }

            for member in members_to_process:
                doc = updated_docs.get(member.id)
                if not doc:
                    continue

                cur_xp    = doc.get("xp", 0)
                cur_level = doc.get("level", 1)
                new_level = cur_level

                # while — бо юзер міг пропустити кілька рівнів одразу
                while cur_xp >= get_level_xp(new_level):
                    cur_xp -= get_level_xp(new_level)
                    new_level += 1

                if new_level != cur_level:
                    # Зберігаємо новий рівень
                    await db.users.update_one(
                        {"guild_id": guild.id, "user_id": member.id},
                        {"$set": {"xp": cur_xp, "level": new_level}},
                    )
                    notify_channel = await get_levelup_channel(guild)
                    if notify_channel:
                        notify = doc.get("levelup_notify", True)
                        await send_level_up(notify_channel, member, new_level, notify=notify)


async def setup(bot):
    await bot.add_cog(ActivityEvents(bot))