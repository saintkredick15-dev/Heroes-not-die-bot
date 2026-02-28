"""
cases.py — Unified Moderation Cases
Заміна старого warns.py. Використовує єдиний сервіс apply_case().
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from modules.db import get_database
from services.moderation import apply_case

db = get_database()
_col_settings = db.guild_settings
_col_cases    = db.cases

E_SHIELD = "🛡️"
E_WARN   = "<:warn:1477376152191373504>"
E_MUTE   = "<:mutemicro:1476200127063396443>"
E_BAN    = "<:ban:1476199074494681170>"
E_CROSS  = "<:cross:1476576718658605086>"
E_SETTING = "<:settings:1476196821444591768>"


# ── Mod Setup UI ─────────────────────────────────────────────────────────────

ACTION_OPTIONS = [
    discord.SelectOption(label="Тайм-аут (Мут)", value="mute", emoji=E_MUTE),
    discord.SelectOption(label="Кік з сервера",   value="kick", emoji="🦵"),
    discord.SelectOption(label="Бан",             value="ban",  emoji=E_BAN),
]

class AddEscalationModal(discord.ui.Modal, title="Ескалація Варнів"):
    warn_count = discord.ui.TextInput(
        label="На якому варні застосувати?", placeholder="3", max_length=2, required=True
    )
    duration = discord.ui.TextInput(
        label="Тривалість мута (годин)", placeholder="24", max_length=3, required=False
    )

    def __init__(self, action: str, view: "ModSetupView"):
        super().__init__()
        self.action = action
        self._view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_count = self.warn_count.value.strip()
        raw_dur   = self.duration.value.strip() or "24"
        if not raw_count.isdigit():
            await interaction.response.send_message(f"{E_CROSS} Невірний формат.", ephemeral=True)
            return

        rule = {
            "count": int(raw_count),
            "action": self.action,
            "duration": int(raw_dur) if raw_dur.isdigit() else 24,
        }

        await _col_settings.update_one(
            {"_id": interaction.guild.id},
            {"$addToSet": {"escalation_rules": rule}},
            upsert=True
        )
        self._view.rules.append(rule)
        await interaction.response.edit_message(embed=_build_setup_embed(self._view.rules), view=self._view)


class ActionSelect(discord.ui.Select):
    def __init__(self, view: "ModSetupView"):
        super().__init__(
            placeholder="Обери дію для нового правила...",
            options=ACTION_OPTIONS,
            row=0
        )
        self._parent = view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AddEscalationModal(self.values[0], self._parent))


def _build_setup_embed(rules: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title=f"{E_SETTING} Система Авто-Ескалації (Automod Cases)",
        description="Налаштуй, що буде з учасником, коли він набере певну кількість варнів.",
        color=0x1a1a2e,
        timestamp=datetime.now(timezone.utc)
    )
    if not rules:
        embed.add_field(name="Сходинки покарань", value=f"{E_CROSS} Не налаштовано", inline=False)
    else:
        lines = []
        for r in sorted(rules, key=lambda x: x["count"]):
            act_lbl = {"mute": f"{E_MUTE} Мут", "kick": "🦵 Кік", "ban": f"{E_BAN} Бан"}.get(r["action"], r["action"])
            dur = f" ({r.get('duration', 24)}h)" if r["action"] == "mute" else ""
            lines.append(f"**{r['count']} варнів** → {act_lbl}{dur}")
        embed.add_field(name="Активні сходинки", value="\n".join(lines), inline=False)
    return embed


class ModSetupView(discord.ui.View):
    def __init__(self, rules: list[dict]):
        super().__init__(timeout=1800)
        self.rules = rules
        self.add_item(ActionSelect(self))

    @discord.ui.button(label="Очистити правила", style=discord.ButtonStyle.danger, custom_id="cls_rules", row=1)
    async def clear_rules(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.rules.clear()
        await _col_settings.update_one(
            {"_id": interaction.guild.id},
            {"$set": {"escalation_rules": []}},
            upsert=True
        )
        await interaction.response.edit_message(embed=_build_setup_embed(self.rules), view=self)


# ── Commands ─────────────────────────────────────────────────────────────────

class CasesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="moderation", description="Налаштування авто-ескалацій")
    @app_commands.default_permissions(administrator=True)
    async def mod_setup(self, interaction: discord.Interaction):
        settings = await _col_settings.find_one({"_id": interaction.guild.id}) or {}
        rules = settings.get("escalation_rules", [])
        await interaction.response.send_message(
            embed=_build_setup_embed(rules), view=ModSetupView(rules), ephemeral=True
        )

    @app_commands.command(name="warn", description="Видати попередження (створити кейс)")
    @app_commands.describe(member="Користувач", reason="Причина")
    @app_commands.default_permissions(moderate_members=True)
    async def warn_cmd(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.defer(ephemeral=False)
        case_id = await apply_case(self.bot, interaction.guild, member, interaction.user, "warn", reason)
        embed = discord.Embed(
            title=f"{E_WARN} Попередження видано",
            description=f"**Учасник:** {member.mention}\n**Причина:** {reason}\n**Case ID:** `#{case_id}`",
            color=0xf39c12
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="history", description="Переглянути історію покарань учасника")
    @app_commands.describe(member="Користувач")
    @app_commands.default_permissions(moderate_members=True)
    async def history_cmd(self, interaction: discord.Interaction, member: discord.Member):
        cases = [c async for c in _col_cases.find({"guild_id": interaction.guild.id, "user_id": member.id}).sort("timestamp", -1).limit(10)]
        embed = discord.Embed(title=f"Історія покарань: {member}", color=0x1a1a2e)
        if not cases:
            embed.description = "✅ Чиста історія."
        else:
            lines = []
            for c in cases:
                ts = c["timestamp"].strftime("%d.%m.%Y")
                act = c.get("action", "warn").upper()
                lines.append(f"`#{c.get('case_id','N/A')}` **{act}** ({ts}) — {c.get('reason', 'Без причини')}")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="delcase", description="Видалити конкретний кейс (або всі)")
    @app_commands.describe(member="Користувач", case_id="ID кейсу (залиш пустим щоб видалити всі)")
    @app_commands.default_permissions(administrator=True)
    async def delcase_cmd(self, interaction: discord.Interaction, member: discord.Member, case_id: str = None):
        if case_id:
            res = await _col_cases.delete_one({"guild_id": interaction.guild.id, "case_id": case_id})
            if res.deleted_count:
                await interaction.response.send_message(f"✅ Case `#{case_id}` видалено.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Case `#{case_id}` не знайдено.", ephemeral=True)
        else:
            res = await _col_cases.delete_many({"guild_id": interaction.guild.id, "user_id": member.id})
            await interaction.response.send_message(f"✅ Історія очищена ({res.deleted_count} кейсів).", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CasesCog(bot))
