from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config.constants import Emojis as _E
from modules.db import get_database
from utils.restrictions import normalize_command_restrictions, normalize_role_ids
from utils.ui_contract import add_section, surface_embed

db = get_database()
_col = db.guild_settings

E_SETTING = _E.SETTINGS.value
E_PIN = _E.PIN.value
E_CROSS = _E.CROSS.value

EXCLUDED_RESTRICTION_COMMANDS = {
    "config",
    "settings",
    "economy_setup",
    "xp_setup",
    "automod",
    "logs_setup",
    "warn_setup",
    "welcome",
    "archive",
    "warns",
    "dev_stats",
    "ticket_setup",
}

PERSONAL_ONLY_COMMANDS = {
    "avatar",
    "auction",
    "daily",
    "faq",
    "help",
    "meme",
    "profile",
    "warnings",
}


async def _get(guild_id: int) -> dict:
    settings = await _col.find_one({"_id": guild_id}) or {}
    restrictions = normalize_command_restrictions(settings.get("command_restrictions"))
    bypass_role_ids = normalize_role_ids(settings.get("command_bypass_role_ids"))
    updates = {}
    if restrictions != settings.get("command_restrictions", {}):
        settings["command_restrictions"] = restrictions
        updates["command_restrictions"] = restrictions
    if bypass_role_ids != settings.get("command_bypass_role_ids", []):
        settings["command_bypass_role_ids"] = bypass_role_ids
        updates["command_bypass_role_ids"] = bypass_role_ids
    if updates:
        await _col.update_one({"_id": guild_id}, {"$set": updates}, upsert=True)
    return settings


async def _set(guild_id: int, data: dict):
    if "command_restrictions" in data:
        data = {**data, "command_restrictions": normalize_command_restrictions(data["command_restrictions"])}
    if "command_bypass_role_ids" in data:
        data = {**data, "command_bypass_role_ids": normalize_role_ids(data["command_bypass_role_ids"])}
    await _col.update_one({"_id": guild_id}, {"$set": data}, upsert=True)


def _feature_enabled_for_command(command: app_commands.Command, settings: dict) -> bool:
    module_name = getattr(getattr(command, "callback", None), "__module__", "")
    if ".economy." not in module_name:
        return True

    eco = settings.get("economy", {}) if isinstance(settings.get("economy"), dict) else {}
    if not eco.get("enabled", True):
        return False

    name = command.name
    if module_name.endswith(".gambling"):
        return eco.get("gambling_enabled", False)
    if module_name.endswith(".auction") or name == "auction":
        return bool(eco.get("auction_channel_id", 0))
    if module_name.endswith(".crime") or name == "crime":
        return eco.get("crime_enabled", True)
    if module_name.endswith(".daily") or name == "daily":
        return eco.get("daily_enabled", True)
    if module_name.endswith(".work") or name == "work":
        return eco.get("work_enabled", True)
    if module_name.endswith(".duel") or name == "duel":
        return eco.get("duel_enabled", True)
    if module_name.endswith(".shop") or name == "shop":
        return eco.get("shop_enabled", True)
    if module_name.endswith(".fonds") or name == "fonds":
        return eco.get("fund_enabled", True)
    if module_name.endswith(".quests") or name.startswith("quest"):
        return eco.get("quests_enabled", True)
    return True


def _is_restrictable_command(command: app_commands.Command, settings: dict) -> bool:
    if not isinstance(command, app_commands.Command):
        return False
    if command.parent is not None:
        return False
    if command.name in EXCLUDED_RESTRICTION_COMMANDS or command.name in PERSONAL_ONLY_COMMANDS:
        return False
    permissions = getattr(command, "default_permissions", None)
    if permissions and permissions.value:
        return False
    module_name = getattr(getattr(command, "callback", None), "__module__", "")
    if ".administration." in module_name:
        return False
    return _feature_enabled_for_command(command, settings)


def _collect_restrictable_commands(bot: commands.Bot, settings: dict) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for command in bot.tree.get_commands():
        if _is_restrictable_command(command, settings):
            catalog[command.name] = command.description or "Користувацька команда"
    return dict(sorted(catalog.items()))


def _build_main_embed(settings: dict) -> discord.Embed:
    embed = surface_embed(
        "admin",
        title=f"{E_SETTING} Налаштування сервера",
        description="Керуйте обмеженнями користувацьких команд по каналах та bypass ролями, які ігнорують ці обмеження.",
    )
    restrictions = settings.get("command_restrictions", {})
    bypass_role_ids = settings.get("command_bypass_role_ids", [])
    lines = []
    for command_name, channel_ids in restrictions.items():
        if channel_ids:
            channel_list = ", ".join(f"<#{channel_id}>" for channel_id in channel_ids)
            lines.append(f"`/{command_name}` -> {channel_list}")
    add_section(
        embed,
        f"{E_PIN} Обмеження команд",
        lines if lines else f"{E_CROSS} Налаштувань ще немає.",
        inline=False,
    )
    add_section(
        embed,
        "Bypass ролі",
        ", ".join(f"<@&{role_id}>" for role_id in bypass_role_ids)
        if bypass_role_ids
        else "Ніхто не ігнорує channel restrictions.",
        inline=False,
    )
    return embed


def _build_command_embed(command_name: str, settings: dict, command_catalog: dict[str, str]) -> discord.Embed:
    description = command_catalog.get(command_name, "Користувацька команда")
    channels = settings.get("command_restrictions", {}).get(command_name, [])
    embed = surface_embed(
        "admin",
        title=f"{E_SETTING} Обмеження: /{command_name}",
        description=f"{description}\n\nОберіть канали, де команда дозволена. Порожній список означає доступ скрізь.",
    )
    add_section(
        embed,
        "Дозволені канали",
        ", ".join(f"<#{channel_id}>" for channel_id in channels) if channels else "Команда доступна в усіх каналах.",
        inline=False,
    )
    return embed


class CommandSelect(discord.ui.Select):
    def __init__(self, command_catalog: dict[str, str]):
        options = [
            discord.SelectOption(label=f"/{name}", description=desc[:100], value=name)
            for name, desc in command_catalog.items()
        ]
        if not options:
            options = [
                discord.SelectOption(
                    label="Команд немає",
                    description="Немає доступних користувацьких команд для обмеження.",
                    value="__empty__",
                )
            ]
        super().__init__(placeholder="Обмежити команду по каналах...", options=options, row=0, disabled=options[0].value == "__empty__")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "__empty__":
            await interaction.response.defer()
            return
        view = CommandRestrictionView(self.view.bot, self.values[0], self.view.settings, self.view.command_catalog)
        await interaction.response.edit_message(
            embed=_build_command_embed(self.values[0], self.view.settings, self.view.command_catalog),
            view=view,
        )


class CommandChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, command_name: str, settings: dict):
        current_ids = settings.get("command_restrictions", {}).get(command_name, [])
        defaults = [discord.Object(id=channel_id) for channel_id in current_ids]
        super().__init__(
            placeholder="Дозволені канали (порожньо = скрізь)...",
            min_values=0,
            max_values=10,
            channel_types=[discord.ChannelType.text],
            row=0,
            default_values=defaults,
        )
        self.command_name = command_name

    async def callback(self, interaction: discord.Interaction):
        channel_ids = [channel.id for channel in self.values] if self.values else []
        settings = self.view.settings
        restrictions = settings.get("command_restrictions", {})
        if channel_ids:
            restrictions[self.command_name] = channel_ids
        else:
            restrictions.pop(self.command_name, None)
        settings["command_restrictions"] = restrictions
        await _set(interaction.guild.id, {"command_restrictions": restrictions})
        if hasattr(interaction.client, "reload_restrictions"):
            await interaction.client.reload_restrictions(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_build_command_embed(self.command_name, settings, self.view.command_catalog),
            view=self.view,
        )


class SettingsView(discord.ui.View):
    def __init__(self, bot: commands.Bot, settings: dict, command_catalog: dict[str, str]):
        super().__init__(timeout=180)
        self.bot = bot
        self.settings = settings
        self.command_catalog = command_catalog
        self.add_item(CommandSelect(command_catalog))

    @discord.ui.button(label="Bypass ролі", style=discord.ButtonStyle.secondary, row=1)
    async def bypass_roles_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BypassRolesView(self.bot, self.settings, self.command_catalog)
        await interaction.response.edit_message(embed=_build_main_embed(self.settings), view=view)


class CommandRestrictionView(discord.ui.View):
    def __init__(self, bot: commands.Bot, command_name: str, settings: dict, command_catalog: dict[str, str]):
        super().__init__(timeout=180)
        self.bot = bot
        self.command_name = command_name
        self.settings = settings
        self.command_catalog = command_catalog
        self.add_item(CommandChannelSelect(command_name, settings))

    @discord.ui.button(label="Скинути", style=discord.ButtonStyle.danger, row=1)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        restrictions = self.settings.get("command_restrictions", {})
        restrictions.pop(self.command_name, None)
        self.settings["command_restrictions"] = restrictions
        await _set(interaction.guild.id, {"command_restrictions": restrictions})
        if hasattr(interaction.client, "reload_restrictions"):
            await interaction.client.reload_restrictions(interaction.guild.id)
        view = SettingsView(self.bot, self.settings, self.command_catalog)
        await interaction.response.edit_message(embed=_build_main_embed(self.settings), view=view)

    @discord.ui.button(label="← Назад", style=discord.ButtonStyle.primary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SettingsView(self.bot, self.settings, self.command_catalog)
        await interaction.response.edit_message(embed=_build_main_embed(self.settings), view=view)


class BypassRoleSelect(discord.ui.RoleSelect):
    def __init__(self, settings: dict):
        current_ids = settings.get("command_bypass_role_ids", [])
        defaults = [discord.Object(id=role_id) for role_id in current_ids]
        super().__init__(
            placeholder="Ролі, які ігнорують channel restrictions...",
            min_values=0,
            max_values=10,
            row=0,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        role_ids = [role.id for role in self.values] if self.values else []
        self.view.settings["command_bypass_role_ids"] = role_ids
        await _set(interaction.guild.id, {"command_bypass_role_ids": role_ids})
        if hasattr(interaction.client, "reload_restrictions"):
            await interaction.client.reload_restrictions(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_main_embed(self.view.settings), view=self.view)


class BypassRolesView(discord.ui.View):
    def __init__(self, bot: commands.Bot, settings: dict, command_catalog: dict[str, str]):
        super().__init__(timeout=180)
        self.bot = bot
        self.settings = settings
        self.command_catalog = command_catalog
        self.add_item(BypassRoleSelect(settings))

    @discord.ui.button(label="Очистити", style=discord.ButtonStyle.danger, row=1)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.settings["command_bypass_role_ids"] = []
        await _set(interaction.guild.id, {"command_bypass_role_ids": []})
        if hasattr(interaction.client, "reload_restrictions"):
            await interaction.client.reload_restrictions(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_main_embed(self.settings), view=self)

    @discord.ui.button(label="← Назад", style=discord.ButtonStyle.primary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SettingsView(self.bot, self.settings, self.command_catalog)
        await interaction.response.edit_message(embed=_build_main_embed(self.settings), view=view)


class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="settings", description="Налаштування сервера: обмеження команд та bypass ролі")
    @app_commands.default_permissions(administrator=True)
    async def settings_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await _get(interaction.guild.id)
        command_catalog = _collect_restrictable_commands(self.bot, settings)
        view = SettingsView(self.bot, settings, command_catalog)
        await interaction.followup.send(embed=_build_main_embed(settings), view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))
