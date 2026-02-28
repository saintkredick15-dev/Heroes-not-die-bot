"""
logs_setup.py — Панель налаштування логів + Audit Log listeners.

Команда: /logs setup
Логи: Модерація, Сервер, Учасники.
Статистика: вибір каналу та інтервалу публікації (1-30 днів).
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from modules.db import get_database

db = get_database()
_col = db.guild_settings

# ── Emoji ────────────────────────────────────────────────────────────────────
E_WARN    = "<:warn:1477376152191373504>"
E_MUTE    = "<:mutemicro:1476200127063396443>"
E_BAN     = "<:ban:1476199074494681170>"
E_MEMBERS = "<:autorole:1476198471307624530>"
E_CHAT    = "<:chat:1475953787687403716>"
E_COINS   = "<:coins:1477376020318388274>"
E_CROSS   = "<:krestik:1476693091355463842>"
E_SETTING = "<:settings:1476196821444591768>"


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get(guild_id: int) -> dict:
    return await _col.find_one({"_id": guild_id}) or {}


async def _set(guild_id: int, data: dict):
    await _col.update_one({"_id": guild_id}, {"$set": data}, upsert=True)


def _ch_name(guild: discord.Guild, ch_id: int | None) -> str:
    if not ch_id:
        return f"{E_CROSS} не вказано"
    ch = guild.get_channel(ch_id)
    return f"<#{ch_id}>" if ch else f"{E_CROSS} канал не знайдено"


def _build_embed(guild: discord.Guild, settings: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"{E_SETTING} Налаштування логів",
        description="Обери канали для кожної категорії логів нижче.",
        color=0x1a1a2e,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name=f"{E_BAN}  Модерація (бани, мути, кіки)",
        value=_ch_name(guild, settings.get("log_mod_channel")),
        inline=False,
    )
    embed.add_field(
        name=f"{E_SETTING} Сервер (канали, ролі)",
        value=_ch_name(guild, settings.get("log_server_channel")),
        inline=False,
    )
    embed.add_field(
        name=f"{E_MEMBERS}  Учасники (вхід/вихід/нік)",
        value=_ch_name(guild, settings.get("log_members_channel")),
        inline=False,
    )
    interval = settings.get("stats_interval_days", 7)
    embed.add_field(
        name=f"{E_CHAT}  Статистика",
        value=(
            f"Канал: {_ch_name(guild, settings.get('stats_channel'))}\n"
            f"Інтервал: **{interval} днів**"
        ),
        inline=False,
    )
    embed.set_footer(text="Vangard Logs · тільки для адміністраторів")
    return embed


# ── Interval Modal ────────────────────────────────────────────────────────────

class IntervalModal(discord.ui.Modal, title="Інтервал статистики"):
    interval = discord.ui.TextInput(
        label="Кожні скільки днів публікувати? (1–30)",
        placeholder="7",
        max_length=2,
        required=True,
    )

    def __init__(self, view: "LogsDashboardView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.interval.value.strip()
        if not raw.isdigit() or not (1 <= int(raw) <= 30):
            await interaction.response.send_message(
                f"{E_CROSS} Введи число від 1 до 30.", ephemeral=True
            )
            return
        days = int(raw)
        await _set(interaction.guild.id, {"stats_interval_days": days})
        self.view.settings["stats_interval_days"] = days
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings),
            view=self.view,
        )


# ── ChannelSelect items ──────────────────────────────────────────────────────
# Використовуємо ChannelSelect напряму через add_item() — це стабільний патерн

class _ModLogSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Канал логів Модерації...",
            min_values=0,
            max_values=1,
            custom_id="log_mod",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        ch_id = self.values[0].id if self.values else None
        await _set(interaction.guild.id, {"log_mod_channel": ch_id})
        self.view.settings["log_mod_channel"] = ch_id
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings), view=self.view
        )


class _ServerLogSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Канал логів Сервера...",
            min_values=0,
            max_values=1,
            custom_id="log_server",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        ch_id = self.values[0].id if self.values else None
        await _set(interaction.guild.id, {"log_server_channel": ch_id})
        self.view.settings["log_server_channel"] = ch_id
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings), view=self.view
        )


class _MembersLogSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Канал логів Учасників...",
            min_values=0,
            max_values=1,
            custom_id="log_members",
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        ch_id = self.values[0].id if self.values else None
        await _set(interaction.guild.id, {"log_members_channel": ch_id})
        self.view.settings["log_members_channel"] = ch_id
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings), view=self.view
        )


class _StatsChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Канал публікації Статистики...",
            min_values=0,
            max_values=1,
            custom_id="log_stats",
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        ch_id = self.values[0].id if self.values else None
        await _set(interaction.guild.id, {"stats_channel": ch_id})
        self.view.settings["stats_channel"] = ch_id
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings), view=self.view
        )


# ── Dashboard View ─────────────────────────────────────────────────────────────

class LogsDashboardView(discord.ui.View):
    def __init__(self, settings: dict):
        super().__init__(timeout=1800)
        self.settings = settings
        self.add_item(_ModLogSelect())
        self.add_item(_ServerLogSelect())
        self.add_item(_MembersLogSelect())
        self.add_item(_StatsChannelSelect())

    @discord.ui.button(
        label="⏱ Змінити інтервал",
        style=discord.ButtonStyle.secondary,
        custom_id="log_interval_btn",
        row=4,
    )
    async def set_interval(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(IntervalModal(self))


# ── Audit Log Listeners ───────────────────────────────────────────────────────

class LogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _mod_log(self, guild: discord.Guild) -> discord.TextChannel | None:
        s = await _get(guild.id)
        ch = guild.get_channel(s.get("log_mod_channel") or 0)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _server_log(self, guild: discord.Guild) -> discord.TextChannel | None:
        s = await _get(guild.id)
        ch = guild.get_channel(s.get("log_server_channel") or 0)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _members_log(self, guild: discord.Guild) -> discord.TextChannel | None:
        s = await _get(guild.id)
        ch = guild.get_channel(s.get("log_members_channel") or 0)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _send(self, ch: discord.TextChannel | None, embed: discord.Embed):
        if not ch:
            return
        try:
            await ch.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ── /logs setup ──────────────────────────────────────────────────────────

    @app_commands.command(name="logs", description="Налаштування логів сервера")
    @app_commands.describe(action="Що зробити")
    @app_commands.choices(action=[app_commands.Choice(name="setup", value="setup")])
    @app_commands.default_permissions(administrator=True)
    async def logs_cmd(self, interaction: discord.Interaction, action: str):
        settings = await _get(interaction.guild.id)
        view = LogsDashboardView(settings)
        embed = _build_embed(interaction.guild, settings)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── Учасники ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        ch = await self._members_log(member.guild)
        if not ch:
            return
        acc_age = (datetime.now(timezone.utc) - member.created_at).days
        embed = discord.Embed(
            title=f"{E_MEMBERS}  Учасник приєднався",
            color=0x2ecc71,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Тег", value=member.mention)
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="Вік акаунту", value=f"{acc_age} дн.")
        embed.set_footer(text=f"Учасників на сервері: {member.guild.member_count}")
        await self._send(ch, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        ch = await self._members_log(member.guild)
        if not ch:
            return
        embed = discord.Embed(
            title="🚪  Учасник покинув сервер",
            color=0xe74c3c,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Тег", value=str(member))
        embed.add_field(name="ID", value=member.id)
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            embed.add_field(name="Ролі", value=", ".join(roles), inline=False)
        await self._send(ch, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        ch = await self._members_log(after.guild)
        if not ch:
            return
        if before.display_name != after.display_name:
            embed = discord.Embed(
                title="✏️  Зміна нікнейму",
                color=0xf39c12,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="До", value=before.display_name, inline=True)
            embed.add_field(name="Після", value=after.display_name, inline=True)
            embed.add_field(name="ID", value=after.id, inline=False)
            await self._send(ch, embed)
        added = set(after.roles) - set(before.roles)
        removed = set(before.roles) - set(after.roles)
        if added or removed:
            embed = discord.Embed(
                title="🎭  Зміна ролей",
                color=0x9b59b6,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            if added:
                embed.add_field(name="Додано", value=", ".join(r.mention for r in added))
            if removed:
                embed.add_field(name="Знято", value=", ".join(r.mention for r in removed))
            await self._send(ch, embed)

    # ── Сервер ───────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        ch = await self._server_log(channel.guild)
        if not ch:
            return
        embed = discord.Embed(
            title="➕  Канал створено",
            description=f"{channel.mention} (`{channel.name}`)",
            color=0x2ecc71,
            timestamp=datetime.now(timezone.utc),
        )
        await self._send(ch, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        ch = await self._server_log(channel.guild)
        if not ch:
            return
        embed = discord.Embed(
            title="🗑️  Канал видалено",
            description=f"`{channel.name}`",
            color=0xe74c3c,
            timestamp=datetime.now(timezone.utc),
        )
        await self._send(ch, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        ch = await self._server_log(role.guild)
        if not ch:
            return
        embed = discord.Embed(
            title="➕  Роль створено",
            description=f"{role.mention} (`{role.name}`)",
            color=0x2ecc71,
            timestamp=datetime.now(timezone.utc),
        )
        await self._send(ch, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        ch = await self._server_log(role.guild)
        if not ch:
            return
        embed = discord.Embed(
            title="🗑️  Роль видалено",
            description=f"`{role.name}`",
            color=0xe74c3c,
            timestamp=datetime.now(timezone.utc),
        )
        await self._send(ch, embed)

    # ── Модерація ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        ch = await self._mod_log(guild)
        if not ch:
            return
        embed = discord.Embed(
            title=f"{E_BAN}  Учасника заблоковано",
            color=0xe74c3c,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="Тег", value=str(user))
        embed.add_field(name="ID", value=user.id)
        await self._send(ch, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        ch = await self._mod_log(guild)
        if not ch:
            return
        embed = discord.Embed(
            title="🔓  Учасника розбановано",
            color=0x2ecc71,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="Тег", value=str(user))
        embed.add_field(name="ID", value=user.id)
        await self._send(ch, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LogsCog(bot))
