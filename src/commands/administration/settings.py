"""
/settings — Загальні налаштування сервера.
- Level Up канал
- Обмеження конкретних команд по каналах
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
from utils.ui_contract import add_section, compact_kv, set_surface_footer, surface_embed

db = get_database()
_col = db.guild_settings

E_SETTING = "<:settings:1476196821444591768>"
E_CHECK   = "<:check:1454140864627740834>"
E_CROSS   = "<:krestik:1476693091355463842>"
E_NOTIF   = "<:notification:1476256523519787161>"
RESTRICTABLE_COMMANDS = {
    "meme":        "Випадковий мем з Reddit",
    "avatar":      "Аватар користувача",
    "profile":     "Профіль з XP/рівнем",
    "leaderboard": "Топ учасників",
}

async def _get(guild_id: int) -> dict:
    return await _col.find_one({"_id": guild_id}) or {}

async def _set(guild_id: int, data: dict):
    await _col.update_one({"_id": guild_id}, {"$set": data}, upsert=True)

def _build_main_embed(settings: dict) -> discord.Embed:
    embed = surface_embed(
        "admin",
        title=f"{E_SETTING} Налаштування сервера",
        description="Це вузький server-level центр: level-up канал і обмеження окремих команд по каналах.",
    )

    lu_ch = settings.get("levelup_channel_id")
    lu_status = f"<#{lu_ch}>" if lu_ch else f"{E_CROSS} Вимкнено"
    add_section(embed, f"{E_NOTIF} Level Up", compact_kv("Канал", lu_status), inline=False)

    restrictions = settings.get("command_restrictions", {})
    if restrictions:
        lines = []
        for cmd_name, ch_ids in restrictions.items():
            if ch_ids:
                ch_list = ", ".join(f"<#{c}>" for c in ch_ids)
                lines.append(f"`/{cmd_name}` → {ch_list}")
        if lines:
            add_section(embed, "📌 Обмеження команд", lines, inline=False)
        else:
            add_section(embed, "📌 Обмеження команд", f"{E_CROSS} Не налаштовано.", inline=False)
    else:
        add_section(embed, "📌 Обмеження команд", f"{E_CROSS} Не налаштовано.", inline=False)

    set_surface_footer(embed, "admin", "Для economy, automod, logs, welcome і warnings використовуйте /config.")
    return embed

def _build_cmd_embed(cmd_name: str, settings: dict) -> discord.Embed:
    desc = RESTRICTABLE_COMMANDS.get(cmd_name, "")
    restrictions = settings.get("command_restrictions", {})
    channels = restrictions.get(cmd_name, [])

    embed = surface_embed(
        "admin",
        title=f"{E_SETTING} Обмеження: /{cmd_name}",
        description=f"{desc}\n\nОберіть канали де команда **дозволена**.\n*Пусто = доступна скрізь.*",
    )
    if channels:
        add_section(embed, f"{E_CHECK} Дозволені канали", ", ".join(f"<#{c}>" for c in channels), inline=False)
    else:
        add_section(embed, "Статус", "Доступна в усіх каналах.", inline=False)
    set_surface_footer(embed, "admin", "Тут задаються лише дозволені канали для конкретної команди.")
    return embed

# ── Views ─────────────────────────────────────────────────────────────────────

class SettingsView(discord.ui.View):
    def __init__(self, settings: dict):
        super().__init__(timeout=180)
        self.settings = settings
        self.add_item(LevelUpChannelSelect(settings))
        self.add_item(CommandSelect())

    @discord.ui.button(label="Вимкнути Level Up", style=discord.ButtonStyle.danger, row=2)
    async def disable_lu(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.settings["levelup_channel_id"] = None
        await _set(interaction.guild.id, {"levelup_channel_id": None})
        await interaction.response.edit_message(
            embed=_build_main_embed(self.settings), view=self)

class LevelUpChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, settings: dict):
        current = settings.get("levelup_channel_id")
        defaults = [discord.Object(id=current)] if current else []
        super().__init__(
            placeholder="Канал для Level Up сповіщень...",
            min_values=1, max_values=1,
            channel_types=[discord.ChannelType.text],
            row=0,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        ch_id = self.values[0].id
        self.view.settings["levelup_channel_id"] = ch_id
        await _set(interaction.guild.id, {"levelup_channel_id": ch_id})
        await interaction.response.edit_message(
            embed=_build_main_embed(self.view.settings), view=self.view)

class CommandSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=f"/{name}", description=desc, value=name)
            for name, desc in RESTRICTABLE_COMMANDS.items()
        ]
        super().__init__(placeholder="Обмежити команду по каналах...", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        cmd_name = self.values[0]
        view = CmdRestrictionView(cmd_name, self.view.settings)
        embed = _build_cmd_embed(cmd_name, self.view.settings)
        await interaction.response.edit_message(embed=embed, view=view)

class CmdRestrictionView(discord.ui.View):
    def __init__(self, cmd_name: str, settings: dict):
        super().__init__(timeout=180)
        self.cmd_name = cmd_name
        self.settings = settings
        self.add_item(CmdChannelSelect(cmd_name, settings))

    @discord.ui.button(label="Скинути", style=discord.ButtonStyle.danger, row=1)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        restrictions = self.settings.get("command_restrictions", {})
        restrictions.pop(self.cmd_name, None)
        self.settings["command_restrictions"] = restrictions
        await _set(interaction.guild.id, {"command_restrictions": restrictions})
        if hasattr(interaction.client, "reload_restrictions"):
            await interaction.client.reload_restrictions(interaction.guild.id)
        view = SettingsView(self.settings)
        await interaction.response.edit_message(
            embed=_build_main_embed(self.settings), view=view)

    @discord.ui.button(label="← Назад", style=discord.ButtonStyle.primary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SettingsView(self.settings)
        await interaction.response.edit_message(
            embed=_build_main_embed(self.settings), view=view)

class CmdChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, cmd_name: str, settings: dict):
        self.cmd_name = cmd_name
        restrictions = settings.get("command_restrictions", {})
        current_ids = restrictions.get(cmd_name, [])
        defaults = [discord.Object(id=cid) for cid in current_ids]
        super().__init__(
            placeholder="Дозволені канали (пусто = скрізь)...",
            min_values=0, max_values=10,
            channel_types=[discord.ChannelType.text],
            row=0,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        ids = [ch.id for ch in self.values] if self.values else []
        settings = self.view.settings
        restrictions = settings.get("command_restrictions", {})
        if ids:
            restrictions[self.cmd_name] = ids
        else:
            restrictions.pop(self.cmd_name, None)
        settings["command_restrictions"] = restrictions
        await _set(interaction.guild.id, {"command_restrictions": restrictions})
        if hasattr(interaction.client, "reload_restrictions"):
            await interaction.client.reload_restrictions(interaction.guild.id)
        embed = _build_cmd_embed(self.cmd_name, settings)
        await interaction.response.edit_message(embed=embed, view=self.view)

# ── Cog ───────────────────────────────────────────────────────────────────────

class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="settings", description="Загальні налаштування сервера. Інші модулі винесені в /config")
    @app_commands.default_permissions(administrator=True)
    async def settings_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await _get(interaction.guild.id)
        view = SettingsView(settings)
        embed = _build_main_embed(settings)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))
