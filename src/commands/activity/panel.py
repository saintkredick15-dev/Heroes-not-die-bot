"""
/panel — адмін-панель налаштувань сервера.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database

db = get_database()
_col = db.guild_settings

E_SETTINGS = "<:settings:1476196821444591768>"
EMBED_COLOR = 0x1a1a2e

async def get_guild_settings(guild_id: int) -> dict:
    return await _col.find_one({"_id": guild_id}) or {}


async def update_guild_settings(guild_id: int, data: dict) -> None:
    await _col.update_one({"_id": guild_id}, {"$set": data}, upsert=True)

class MinLevelModal(discord.ui.Modal, title="Налаштування кастомних кольорів"):
    lvl_input = discord.ui.TextInput(
        label="Мінімальний рівень",
        placeholder="10",
        min_length=1,
        max_length=3
    )

    def __init__(self, guild_id: int, current_lvl: int, panel_view: PanelView):
        super().__init__()
        self.guild_id = guild_id
        self.panel_view = panel_view
        self.lvl_input.default = str(current_lvl)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.lvl_input.value)
            if val < 10:
                await interaction.response.send_message("❌ Мінімальний рівень не може бути менше 10!", ephemeral=True)
                return
            await update_guild_settings(self.guild_id, {"color_min_level": val})
            self.panel_view.min_color_level = val
            embed = _build_embed(self.guild_id, self.panel_view.current_channel_id, val)
            await interaction.response.edit_message(embed=embed, view=self.panel_view)
        except ValueError:
            await interaction.response.send_message("❌ Введіть число.", ephemeral=True)

class AnchorRoleModal(discord.ui.Modal, title="Якір для кольорів (ID ролі)"):
    role_id_input = discord.ui.TextInput(
        label="ID ролі-якоря (залишити пустим для скидання)",
        placeholder="123456789...",
        required=False,
    )

    def __init__(self, guild_id: int, current_id: int | None, panel_view: PanelView):
        super().__init__()
        self.guild_id = guild_id
        self.panel_view = panel_view
        if current_id:
            self.role_id_input.default = str(current_id)

    async def on_submit(self, interaction: discord.Interaction):
        val_str = self.role_id_input.value.strip()
        if not val_str:
            await update_guild_settings(self.guild_id, {"color_anchor_role_id": None})
            self.panel_view.anchor_role_id = None
            embed = _build_embed(self.guild_id, self.panel_view.current_channel_id, self.panel_view.min_color_level, None)
            await interaction.response.edit_message(embed=embed, view=self.panel_view)
            return
            
        try:
            val = int(val_str)
            role = interaction.guild.get_role(val)
            if not role:
                await interaction.response.send_message("❌ Роль з таким ID не знайдена на сервері!", ephemeral=True)
                return
                
            await update_guild_settings(self.guild_id, {"color_anchor_role_id": val})
            self.panel_view.anchor_role_id = val
            embed = _build_embed(self.guild_id, self.panel_view.current_channel_id, self.panel_view.min_color_level, val)
            await interaction.response.edit_message(embed=embed, view=self.panel_view)
        except ValueError:
            await interaction.response.send_message("❌ ID ролі має складатись лише з цифр.", ephemeral=True)

class DeployColorSelect(discord.ui.ChannelSelect):
    """Меню вибору каналу для відправки панелі кольорів."""
    def __init__(self):
        super().__init__(
            placeholder="Відправити панель кольорів у канал...",
            min_values=1, max_values=1,
            channel_types=[discord.ChannelType.text],
            custom_id="panel_deploy_color_select"
        )
        self.row = 1

    async def callback(self, interaction: discord.Interaction):
        app_channel = self.values[0]
        actual_channel = interaction.guild.get_channel(app_channel.id)
        
        if not isinstance(actual_channel, discord.TextChannel):
            await interaction.response.send_message("❌ Будь ласка, оберіть текстовий канал.", ephemeral=True)
            return

        from commands.activity.role_picker import ColorPickerView, E_PALETTE, E_CROSS
        embed = discord.Embed(
            title=f"{E_PALETTE} Обери свій колір нікнейма",
            description=f"Ти можеш обрати базовий колір з опцій нижче.\nДосягни потрібного рівня та тисни {E_PALETTE} щоб вказати свій унікальний HEX-код.\nТисни {E_CROSS} щоб повністю зняти свій колір.",
            color=0x1a1a2e
        )
        await actual_channel.send(embed=embed, view=ColorPickerView())
        await interaction.response.send_message(f"✅ Успішно! Панель кольорів відправлена у {actual_channel.mention}", ephemeral=True)

class _LevelupChannelSelect(discord.ui.ChannelSelect):
    """Меню вибору каналу для Level Up сповіщень."""
    def __init__(self):
        super().__init__(
            placeholder="Канал для повідомлень Level Up",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text],
            custom_id="panel_levelup_channel",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        await update_guild_settings(
            self.view.guild_id, {"levelup_channel_id": channel.id}
        )
        self.view.current_channel_id = channel.id
        embed = _build_embed(
            self.view.guild_id, channel.id,
            self.view.min_color_level, self.view.anchor_role_id
        )
        await interaction.response.edit_message(embed=embed, view=self.view)


class PanelView(discord.ui.View):
    """Головна view панелі з вибором каналу level-up сповіщень."""

    def __init__(self, guild_id: int, current_channel_id: int | None, min_color_lvl: int, anchor_role_id: int | None):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.current_channel_id = current_channel_id
        self.min_color_level = min_color_lvl
        self.anchor_role_id = anchor_role_id

        self.add_item(_LevelupChannelSelect())
        self.add_item(DeployColorSelect())

    @discord.ui.button(
        label="Мін. рівень для кольорів",
        style=discord.ButtonStyle.secondary,
        custom_id="panel_color_min_lvl",
        row=2,
    )
    async def set_color_level(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MinLevelModal(self.guild_id, self.min_color_level, self))

    @discord.ui.button(
        label="Налаштувати Якір (ID ролі)",
        style=discord.ButtonStyle.secondary,
        custom_id="panel_color_anchor",
        row=2,
    )
    async def set_anchor_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AnchorRoleModal(self.guild_id, self.anchor_role_id, self))

    @discord.ui.button(
        label="Вимкнути Level Up сповіщення",
        style=discord.ButtonStyle.danger,
        custom_id="panel_levelup_disable",
        row=3,
    )
    async def disable_levelup(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await update_guild_settings(self.guild_id, {"levelup_channel_id": None})
        self.current_channel_id = None

        embed = _build_embed(self.guild_id, None, self.min_color_level, self.anchor_role_id)
        await interaction.response.edit_message(embed=embed, view=self)

def _build_embed(guild_id: int, levelup_channel_id: int | None, min_color_lvl: int, anchor_role_id: int | None) -> discord.Embed:
    if levelup_channel_id:
        levelup_status = f"<#{levelup_channel_id}>"
    else:
        levelup_status = "Вимкнено"

    embed = discord.Embed(
        title=f"{E_SETTINGS}  Панель налаштувань",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Level Up сповіщення",
        value=(
            f"Канал: **{levelup_status}**\n"
            "⎿ Повідомлення надсилається коли юзер підвищується в рівні."
        ),
        inline=False,
    )
    anchor_display = f"<@&{anchor_role_id}>" if anchor_role_id else "**Не встановлено** (створюватимуться під роллю бота)"
    embed.add_field(
        name="Кольори нікнеймів",
        value=(
            f"⎿ Система кастомних кольорів (Color Role Picker).\n"
            f"⎿ Мін. рівень для HEX-вводу: **{min_color_lvl}**\n"
            f"⎿ Якір: {anchor_display}\n\n"
            f"**ℹ️ Інструкція:** Створіть порожню роль `--- Colors ---` і вкажіть її ID тут. Бот створюватиме кольори рівно під нею. Звичайна структура (зверху вниз): Адмін -> Роль бота (`Vangard`) ⚠️ **(роль бота ОБОВ'ЯЗКОВО має бути вище за якір)** -> Якір -> Кольори -> Звичайні гравці.\n"
        ),
        inline=False,
    )
    embed.set_footer(text="Налаштування зберігаються автоматично")
    return embed

class PanelCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="panel",
        description="Панель налаштувань сервера (адмін)",
    )
    @app_commands.default_permissions(administrator=True)
    async def panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)  # Відповідаємо одразу, до DB
        settings = await get_guild_settings(interaction.guild.id)
        levelup_channel_id = settings.get("levelup_channel_id")
        min_color_lvl = settings.get("color_min_level", 10)
        anchor_role_id = settings.get("color_anchor_role_id")

        embed = _build_embed(interaction.guild.id, levelup_channel_id, min_color_lvl, anchor_role_id)
        view  = PanelView(interaction.guild.id, levelup_channel_id, min_color_lvl, anchor_role_id)

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)



async def setup(bot):
    await bot.add_cog(PanelCommands(bot))
