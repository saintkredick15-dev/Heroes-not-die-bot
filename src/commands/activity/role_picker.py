"""
role_picker.py
Система самовидачі кольорових ролей.
"""
from __future__ import annotations

import re
import asyncio
import discord
from discord.ext import commands
from modules.db import get_database
from repositories.user import get_user

db = get_database()

E_PALETTE   = "<:palette:1485608515409285140>"
E_CROSS     = "<:close:1485598320935174317>"
EMBED_COLOR = 0x1a1a2e

PRESETS = {
    "Red":     ("#E74C3C", "🔴"),
    "Orange":  ("#E67E22", "🟠"),
    "Yellow":  ("#F1C40F", "🟡"),
    "Green":   ("#2ECC71", "🟢"),
    "Cyan":    ("#1ABC9C", "🧊"),
    "Blue":    ("#3498DB", "🔵"),
    "Purple":  ("#9B59B6", "🟣"),
    "Pink":    ("#FF69B4", "🌸"),
    "White":   ("#FFFFFF", "⚪"),
    "Dark":    ("#2C3E50", "⚫"),
}

def _is_color_role(role: discord.Role) -> bool:
    if role.permissions.value != 0:
        return False
    name = role.name
    if name in PRESETS:
        return True
    if re.match(r"^#[0-9A-F]{6}$", name):
        return True
    return False

async def _remove_old_colors(member: discord.Member):
    to_remove = [r for r in member.roles if _is_color_role(r)]
    if to_remove:
        try:
            await member.remove_roles(*to_remove, reason="Зміна/зняття кольору нікнейма")
        except discord.Forbidden:
            pass

async def _assign_color_role(interaction: discord.Interaction, name: str, hex_color: str):
    
    if interaction.response.is_done():
        return
    try:
        await interaction.response.defer(ephemeral=True)
    except (discord.NotFound, discord.HTTPException):
        return  

    guild  = interaction.guild
    member = interaction.user

    base_role = guild.me.top_role
    settings  = await db.guild_settings.find_one({"_id": guild.id}) or {}
    anchor_id = settings.get("color_anchor_role_id")
    if anchor_id:
        anchor_role = guild.get_role(anchor_id)
        if anchor_role:
            base_role = anchor_role

    role = discord.utils.get(guild.roles, name=name)

    if not role:
        try:
            int_color = int(hex_color.lstrip("#"), 16)
            role = await guild.create_role(
                name=name,
                color=discord.Color(int_color),
                permissions=discord.Permissions.none(),
                mentionable=False,
                reason=f"Кольорова роль для {member.display_name}",
            )
            await asyncio.sleep(0.3)

            try:
                roles = [r for r in guild.roles if r.id != guild.id and r.id != role.id]
                roles.sort(key=lambda r: r.position)
                base_idx = next(i for i, r in enumerate(roles) if r.id == base_role.id)
                roles.insert(base_idx, role)
                await guild.edit_role_positions({r: i + 1 for i, r in enumerate(roles)})
            except (StopIteration, Exception):
                pass

        except discord.Forbidden:
            await interaction.followup.send("<:close:1485598320935174317> У бота немає прав керувати ролями!", ephemeral=True)
            return
        except (ValueError, discord.HTTPException) as e:
            await interaction.followup.send(f"<:close:1485598320935174317> Помилка при створенні ролі: {e}", ephemeral=True)
            return

    await _remove_old_colors(member)

    try:
        await member.add_roles(role, reason=f"Колір нікнейма: {name}")
        await interaction.followup.send(f"<:check:1485597845883981905> Колір встановлено: **{name}**", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(
            "<:close:1485598320935174317> Не вдалося видати роль — перевір позицію ролі бота.", ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"<:close:1485598320935174317> Помилка: {type(e).__name__}", ephemeral=True)

class CustomHexModal(discord.ui.Modal, title="Кастомний колір нікнейма"):
    hex_input = discord.ui.TextInput(
        label="Введи HEX-код (наприклад: #e91e63)",
        placeholder="#...",
        max_length=7,
        min_length=6,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        color_str = self.hex_input.value.strip().upper()
        if not re.match(r"^#?[0-9A-F]{6}$", color_str):
            await interaction.response.send_message(
                "<:close:1485598320935174317> Некоректний формат. Введи 6 символів HEX, наприклад `#E91E63`.",
                ephemeral=True,
            )
            return
        if not color_str.startswith("#"):
            color_str = "#" + color_str
        await _assign_color_role(interaction, name=color_str, hex_color=color_str)

class PredefinedColorSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, value=name, emoji=emoji)
            for name, (hex_code, emoji) in PRESETS.items()
        ]
        super().__init__(
            placeholder="Обери базовий колір...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="colorpicker_select",
        )

    async def callback(self, interaction: discord.Interaction):
        choice_name = self.values[0]
        await _assign_color_role(interaction, name=choice_name, hex_color=PRESETS[choice_name][0])

class ColorPickerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PredefinedColorSelect())

    @discord.ui.button(
        label="Кастомний HEX-колір",
        emoji=discord.PartialEmoji.from_str(E_PALETTE),
        style=discord.ButtonStyle.secondary,
        custom_id="colorpicker_custom_btn",
    )
    async def custom_hex_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings   = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        min_level  = settings.get("color_min_level", 10)
        user_data  = await get_user(db, interaction.guild.id, interaction.user.id)
        user_level = user_data.get("level", 1)

        if user_level < min_level:
            await interaction.response.send_message(
                f"<:close:1485598320935174317> Для кастомних кольорів потрібен **рівень {min_level}** (твій: {user_level}).",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(CustomHexModal())

    @discord.ui.button(
        label="Зняти колір",
        emoji=discord.PartialEmoji.from_str(E_CROSS),
        style=discord.ButtonStyle.secondary,
        custom_id="colorpicker_remove_btn",
    )
    async def remove_color_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        member     = interaction.user
        has_colors = any(_is_color_role(r) for r in member.roles)

        if not has_colors:
            await interaction.response.send_message("<:close:1485598320935174317> В тебе немає кольорової ролі.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await _remove_old_colors(member)
        await interaction.followup.send("<:check:1485597845883981905> Твій колір знято.", ephemeral=True)

class RolePickerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

async def setup(bot):
    await bot.add_cog(RolePickerCommands(bot))
    bot.add_view(ColorPickerView())
