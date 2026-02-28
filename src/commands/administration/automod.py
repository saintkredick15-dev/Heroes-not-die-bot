"""
automod.py
Команди для налаштування правил Автомодерації.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from modules.db import get_database
from services.automod import reload_guild_automod_cache

db = get_database()
_col_settings = db.guild_settings

E_SHIELD  = "🛡️"
E_CROSS   = "<:cross:1476576718658605086>"
E_SETTING = "<:settings:1476196821444591768>"


class AddAutomodRuleModal(discord.ui.Modal, title="Нове правило Автомода"):
    trigger = discord.ui.TextInput(
        label="Тригер (Слово чи Тег)",
        placeholder="приклад.gg / AZOV",
        max_length=32,
        required=True
    )
    reason = discord.ui.TextInput(
        label="Причина для кейсу",
        placeholder="Реклама стороннього сервера",
        max_length=128,
        required=True
    )

    def __init__(self, action: str, view: "AutomodDashboardView"):
        super().__init__()
        self.action = action
        self._view = view

    async def on_submit(self, interaction: discord.Interaction):
        trig = self.trigger.value.strip()
        rule = {
            "trigger": trig,
            "action": self.action,
            "reason": self.reason.value.strip()
        }

        self._view.rules.append(rule)
        await _col_settings.update_one(
            {"_id": interaction.guild.id},
            {"$set": {"automod_rules": self._view.rules}},
            upsert=True
        )
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_automod_embed(self._view.rules), view=self._view)


class AutomodActionSelect(discord.ui.Select):
    def __init__(self, view: "AutomodDashboardView"):
        super().__init__(
            placeholder="Обери дію для нового тригера...",
            options=[
                discord.SelectOption(label="Видати Варн", value="warn", emoji=E_SHIELD),
                discord.SelectOption(label="Кікнути", value="kick", emoji="🦵"),
                discord.SelectOption(label="Забанити", value="ban", emoji="🔨"),
            ],
            row=0
        )
        self._parent = view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AddAutomodRuleModal(self.values[0], self._parent))


def _build_automod_embed(rules: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title=f"{E_SETTING} Vangard Automod Engine",
        description="Налаштуй фільтри (слова, посилання, теги), які Автомод миттєво збиватиме і застосовуватиме покарання (генеруватиме Cases).",
        color=0x1a1a2e,
        timestamp=datetime.now(timezone.utc)
    )
    if not rules:
        embed.add_field(name="Активні фільтри", value=f"{E_CROSS} Список порожній.", inline=False)
    else:
        lines = []
        for r in rules:
            act_lbl = {"warn": f"{E_SHIELD} Варн", "kick": "🦵 Кік", "ban": "🔨 Бан"}.get(r["action"], r["action"])
            lines.append(f"**[{r['trigger']}]** → {act_lbl}\n↳ *Причина:* {r.get('reason', '—')}")
        embed.add_field(name="Активні фільтри", value="\n\n".join(lines), inline=False)
    return embed


class AutomodDashboardView(discord.ui.View):
    def __init__(self, rules: list[dict]):
        super().__init__(timeout=1800)
        self.rules = rules
        self.add_item(AutomodActionSelect(self))

    @discord.ui.button(label="Очистити всі фільтри", style=discord.ButtonStyle.danger, custom_id="am_clear", row=1)
    async def clear_rules(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.rules.clear()
        await _col_settings.update_one(
            {"_id": interaction.guild.id},
            {"$set": {"automod_rules": []}},
            upsert=True
        )
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_automod_embed(self.rules), view=self)


class AutomodCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="automod", description="Налаштування двигуна Автомодерації")
    @app_commands.default_permissions(administrator=True)
    async def automod_cmd(self, interaction: discord.Interaction):
        settings = await _col_settings.find_one({"_id": interaction.guild.id}) or {}
        rules = settings.get("automod_rules", [])
        await interaction.response.send_message(
            embed=_build_automod_embed(rules), view=AutomodDashboardView(rules), ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AutomodCog(bot))
