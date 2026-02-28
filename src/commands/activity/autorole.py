"""
Система авто-ролей.

Функціонал:
- Вибір ролі через RoleSelect АБО Modal (введення назви/ID)
- Виключення конкретних учасників (UserSelect)
- «Застосувати зараз» — батчова видача fetch_members (не тільки кеш)
"""
from __future__ import annotations
import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database

db = get_database()
_col = db.autorole_config

# ── Кастомні емодзі ──────────────────────────────────────────────────────────
E_AUTOROLE = "<:autorole:1476198471307624530>"
E_SETTINGS = "<:settings:1476196821444591768>"

EMBED_COLOR = 0x1a1a2e


async def _get_config(guild_id: int) -> dict:
    return await _col.find_one({"guild_id": guild_id}) or {}


# ── Modal для ролі вручну ─────────────────────────────────────────────────────

class RoleByNameModal(discord.ui.Modal, title="Вказати роль вручну"):
    role_input = discord.ui.TextInput(
        label="Назва або ID ролі",
        placeholder="Приклад: Member  або  1234567890123456789",
        max_length=100,
    )

    def __init__(self, view: "AutoRoleView"):
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction):
        query = self.role_input.value.strip()
        guild = interaction.guild

        role: discord.Role | None = None
        if query.isdigit():
            role = guild.get_role(int(query))
        if not role:
            role = discord.utils.find(lambda r: r.name.lower() == query.lower(), guild.roles)
        if not role:
            role = discord.utils.find(lambda r: query.lower() in r.name.lower(), guild.roles)

        if not role:
            await interaction.response.send_message(
                f"❌ Роль **«{query}»** не знайдена. Спробуй ввести точну назву або ID.",
                ephemeral=True,
            )
            return

        self._view.selected_role_id = role.id
        await interaction.response.send_message(
            f"✅ Роль **{role.name}** обрана! Натисни «Зберегти».",
            ephemeral=True,
        )


# ── View ──────────────────────────────────────────────────────────────────────

class AutoRoleView(discord.ui.View):
    def __init__(self, current_role_id: int | None, excluded_user_ids: list[int]):
        super().__init__(timeout=180)
        self.selected_role_id: int | None = current_role_id
        self.excluded_user_ids: list[int] = list(excluded_user_ids)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Авто-роль для новачків...",
        min_values=0, max_values=1, row=0,
    )
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        if select.values:
            self.selected_role_id = select.values[0].id
            await interaction.response.send_message(
                f"✅ Обрано **{select.values[0].name}**. Натисни «Зберегти».", ephemeral=True
            )
        else:
            self.selected_role_id = None
            await interaction.response.send_message("✅ Роль знята.", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Виключення: хто НЕ отримає роль (до 10)...",
        min_values=0, max_values=10, row=1,
    )
    async def exclude_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.excluded_user_ids = [u.id for u in select.values]
        if select.values:
            mentions = ", ".join(u.mention for u in select.values)
            await interaction.response.send_message(
                f"Виключено: {mentions}\nНатисни «Зберегти».", ephemeral=True
            )
        else:
            await interaction.response.send_message("✅ Виключення очищено.", ephemeral=True)

    @discord.ui.button(label="Ввести назву/ID ролі", style=discord.ButtonStyle.secondary, row=2)
    async def role_by_name_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RoleByNameModal(view=self))

    @discord.ui.button(label="Зберегти", style=discord.ButtonStyle.primary, row=3)
    async def save_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_role_id:
            await interaction.response.send_message("❌ Спочатку обери роль.", ephemeral=True)
            return

        role = interaction.guild.get_role(self.selected_role_id)
        if not role:
            await interaction.response.send_message("❌ Роль не знайдена.", ephemeral=True)
            return

        await _col.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {
                "guild_id": interaction.guild.id,
                "role_id": role.id,
                "excluded_user_ids": self.excluded_user_ids,
                "enabled": True,
            }},
            upsert=True,
        )

        excl = (
            "\n" + " ".join(f"<@{uid}>" for uid in self.excluded_user_ids)
            if self.excluded_user_ids else "\nВиключень немає."
        )
        await interaction.response.send_message(
            f"✅ Роль **{role.name}** збережена.{excl}", ephemeral=True
        )

    @discord.ui.button(label="Застосувати зараз", style=discord.ButtonStyle.success, row=3)
    async def apply_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await _get_config(interaction.guild.id)
        role_id = config.get("role_id")
        if not role_id:
            await interaction.response.send_message("❌ Авто-роль не налаштована.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("❌ Роль не знайдена.", ephemeral=True)
            return

        excluded_ids: set[int] = set(config.get("excluded_user_ids", []))
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Завантаження повного списку учасників...", ephemeral=True)

        # fetch_members = реальний API, не тільки кеш
        targets: list[discord.Member] = []
        async for member in interaction.guild.fetch_members(limit=None):
            if not member.bot and member.id not in excluded_ids and role not in member.roles:
                targets.append(member)

        added = skipped = 0
        for chunk in [targets[i:i + 10] for i in range(0, len(targets), 10)]:
            results = await asyncio.gather(
                *[m.add_roles(role, reason="autorole: apply all") for m in chunk],
                return_exceptions=True,
            )
            added   += sum(1 for r in results if not isinstance(r, Exception))
            skipped += sum(1 for r in results if isinstance(r, Exception))
            await asyncio.sleep(0.5)

        excl_note = f"\nВиключено: **{len(excluded_ids)}**" if excluded_ids else ""
        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_author(name="Авто-роль — результат")
        embed.description = (
            f"Роль **{role.name}** видана:\n"
            f"› Знайдено без ролі: **{len(targets)}**\n"
            f"› Отримали: **{added}**\n"
            f"› Помилка: **{skipped}**"
            f"{excl_note}"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Скинути", style=discord.ButtonStyle.danger, row=3)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _col.delete_one({"guild_id": interaction.guild.id})
        self.selected_role_id = None
        self.excluded_user_ids = []
        await interaction.response.send_message("Авто-роль відключена.", ephemeral=True)


# ── Cog ───────────────────────────────────────────────────────────────────────

class AutoRoleSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await _col.create_index("guild_id", unique=True, background=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        config = await _get_config(member.guild.id)
        if not config.get("enabled") or not config.get("role_id"):
            return
        if member.id in set(config.get("excluded_user_ids", [])):
            return
        role = member.guild.get_role(config["role_id"])
        if not role:
            return
        try:
            await member.add_roles(role, reason="autorole: member join")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @app_commands.command(name="autorole", description="Налаштування авто-ролі для нових учасників")
    @app_commands.default_permissions(administrator=True)
    async def autorole(self, interaction: discord.Interaction):
        config = await _get_config(interaction.guild.id)
        role_id = config.get("role_id")
        role    = interaction.guild.get_role(role_id) if role_id else None
        enabled = config.get("enabled", False)
        excluded_ids: list[int] = config.get("excluded_user_ids", [])

        status = (
            f"{role.mention} — {'✅ увімкнено' if enabled else '⏸ вимкнено'}"
            if role else "не налаштована"
        )
        excl_text = (
            " ".join(f"<@{uid}>" for uid in excluded_ids[:5])
            + ("..." if len(excluded_ids) > 5 else "")
            if excluded_ids else "немає"
        )

        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_author(name="Авто-роль")
        embed.description = (
            f"{E_AUTOROLE}  **Роль:** {status}\n"
            f"**Виключення:** {excl_text}\n\n"
            "**Рядок 1** — обери роль для новачків.\n"
            "**Рядок 2** — обери учасників-виключення (до 10).\n"
            "якщо ролей 100+, введи назву/ID вручну."
        )
        view = AutoRoleView(current_role_id=role_id, excluded_user_ids=excluded_ids)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AutoRoleSystem(bot))
