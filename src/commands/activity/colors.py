"""
/colors — Налаштування системи кольорів нікнеймів.
Деплой панелі кольорів, мін. рівень, якір ролі.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database

db = get_database()
_col = db.guild_settings

E_PALETTE  = "<:palette:1476196821444591768>"
E_CROSS    = "<:krestik:1476693091355463842>"
EMBED_COLOR = 0x1a1a2e

async def _get(guild_id: int) -> dict:
    return await _col.find_one({"_id": guild_id}) or {}

async def _set(guild_id: int, data: dict):
    await _col.update_one({"_id": guild_id}, {"$set": data}, upsert=True)

def _build_embed(settings: dict) -> discord.Embed:
    min_lvl = settings.get("color_min_level", 10)
    anchor_id = settings.get("color_anchor_role_id")
    anchor_text = f"<@&{anchor_id}>" if anchor_id else "**Не встановлено** (буде під роллю бота)"

    embed = discord.Embed(
        title="🎨 Кольори нікнеймів",
        description=(
            "Система кастомних кольорів (Color Role Picker).\n"
            f"Мін. рівень для HEX-вводу: **{min_lvl}**\n"
            f"Якір: {anchor_text}\n\n"
            "**Інструкція:** Створіть порожню роль `--- Colors ---` і вкажіть її ID.\n"
            "Бот створюватиме кольори рівно під нею.\n"
            "Роль бота **обов'язково** має бути вище якоря."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="Налаштування зберігаються автоматично")
    return embed

# ── Modals ────────────────────────────────────────────────────────────────────

class MinLevelModal(discord.ui.Modal, title="Мінімальний рівень"):
    lvl_input = discord.ui.TextInput(
        label="Мін. рівень для HEX-кольору",
        placeholder="10",
        min_length=1,
        max_length=3,
    )

    def __init__(self, view):
        super().__init__()
        self.color_view = view
        self.lvl_input.default = str(view.settings.get("color_min_level", 10))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.lvl_input.value)
            if val < 1:
                return await interaction.response.send_message(f"{E_CROSS} Мінімум 1.", ephemeral=True)
            self.color_view.settings["color_min_level"] = val
            await _set(interaction.guild.id, {"color_min_level": val})
            await interaction.response.edit_message(
                embed=_build_embed(self.color_view.settings), view=self.color_view)
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Введіть число.", ephemeral=True)

class AnchorRoleModal(discord.ui.Modal, title="Якір для кольорів"):
    role_input = discord.ui.TextInput(
        label="ID ролі-якоря (пусто = скинути)",
        placeholder="123456789...",
        required=False,
    )

    def __init__(self, view):
        super().__init__()
        self.color_view = view
        current = view.settings.get("color_anchor_role_id")
        if current:
            self.role_input.default = str(current)

    async def on_submit(self, interaction: discord.Interaction):
        val_str = self.role_input.value.strip()
        if not val_str:
            self.color_view.settings["color_anchor_role_id"] = None
            await _set(interaction.guild.id, {"color_anchor_role_id": None})
            await interaction.response.edit_message(
                embed=_build_embed(self.color_view.settings), view=self.color_view)
            return

        try:
            val = int(val_str)
            role = interaction.guild.get_role(val)
            if not role:
                return await interaction.response.send_message(f"{E_CROSS} Роль не знайдена.", ephemeral=True)
            self.color_view.settings["color_anchor_role_id"] = val
            await _set(interaction.guild.id, {"color_anchor_role_id": val})
            await interaction.response.edit_message(
                embed=_build_embed(self.color_view.settings), view=self.color_view)
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} ID має бути числом.", ephemeral=True)

# ── View ──────────────────────────────────────────────────────────────────────

class ColorsView(discord.ui.View):
    def __init__(self, settings: dict):
        super().__init__(timeout=180)
        self.settings = settings
        self.add_item(DeployColorSelect())

    @discord.ui.button(label="Мін. рівень для кольорів", style=discord.ButtonStyle.secondary, row=1)
    async def min_level_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MinLevelModal(self))

    @discord.ui.button(label="Налаштувати Якір (ID ролі)", style=discord.ButtonStyle.secondary, row=1)
    async def anchor_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AnchorRoleModal(self))

class DeployColorSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Відправити панель кольорів у канал...",
            min_values=1, max_values=1,
            channel_types=[discord.ChannelType.text],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(self.values[0].id)
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message(f"{E_CROSS} Оберіть текстовий канал.", ephemeral=True)

        from commands.activity.role_picker import ColorPickerView, E_PALETTE, E_CROSS
        embed = discord.Embed(
            title=f"{E_PALETTE} Обери свій колір нікнейма",
            description=f"Обери базовий колір з опцій нижче.\nДосягни рівня та тисни {E_PALETTE} для HEX.\nТисни {E_CROSS} щоб зняти колір.",
            color=0x1a1a2e,
        )
        await ch.send(embed=embed, view=ColorPickerView())
        await interaction.response.send_message(f"✅ Панель кольорів відправлена у {ch.mention}", ephemeral=True)

# ── Cog ───────────────────────────────────────────────────────────────────────

class ColorsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="colors", description="Налаштування системи кольорів нікнеймів")
    @app_commands.default_permissions(administrator=True)
    async def colors_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await _get(interaction.guild.id)
        view = ColorsView(settings)
        embed = _build_embed(settings)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ColorsCog(bot))
