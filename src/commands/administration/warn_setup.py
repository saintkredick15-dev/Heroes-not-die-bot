"""
warn_setup.py — Панель налаштування попереджень (Smart Panel V14).
Ескалації + налаштування спадання (decay) варнів.
"""
import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database

db = get_database()
_col = db.guild_settings

# ── Емодзі ────────────────────────────────────────────────────────────────────
E_WARN    = "<:warning:1485598476850040843>"
E_CROSS   = "<:close:1485598320935174317>"
E_CHECK   = "<:check:1485597845883981905>"
E_SETTING = "<:settings:1485606007668342865>"

EMBED_COLOR = 0x1a1a2e

ACTION_LABELS = {
    "mute": "🔇 Мут",
    "kick": "👢 Кік",
    "ban": "🔨 Бан",
}

async def _get(guild_id: int) -> dict:
    return await _col.find_one({"_id": guild_id}) or {}

def _build_embed(settings: dict) -> discord.Embed:
    rules = settings.get("warn_escalation", [])
    decay_days = settings.get("warn_decay_days", 0)

    embed = discord.Embed(
        title=f"{E_WARN} Налаштування Попереджень",
        description="Визначте, що відбувається при накопиченні попереджень.",
        color=EMBED_COLOR,
    )

    if not rules:
        embed.add_field(
            name="Правила ескалації",
            value=f"{E_CROSS} Не налаштовано.\nНатисніть **Додати правило** нижче.",
            inline=False,
        )
    else:
        sorted_rules = sorted(rules, key=lambda r: r["count"])
        lines = []
        for i, r in enumerate(sorted_rules, 1):
            action_label = ACTION_LABELS.get(r["action"], r["action"])
            duration = r.get("duration", "")
            if duration:
                lines.append(f"`{i}.` **{r['count']}** варнів → {action_label} на **{duration}**")
            else:
                lines.append(f"`{i}.` **{r['count']}** варнів → {action_label}")
        embed.add_field(name="Правила ескалації", value="\n".join(lines), inline=False)

    if decay_days > 0:
        embed.add_field(
            name=f"{E_SETTING} Спадання варнів",
            value=f"Попередження старіші за **{decay_days}** днів не враховуються для ескалації.",
            inline=False,
        )
    else:
        embed.add_field(
            name=f"{E_SETTING} Спадання варнів",
            value=f"{E_CROSS} Вимкнено (варни не спадають).",
            inline=False,
        )

    return embed

# ── Modals ────────────────────────────────────────────────────────────────────

class AddRuleModal(discord.ui.Modal, title="Додати правило ескалації"):
    warn_count = discord.ui.TextInput(
        label="Кількість попереджень (1-50)",
        placeholder="3",
        max_length=2,
        required=True,
    )
    action_input = discord.ui.TextInput(
        label="Дія: mute / kick / ban",
        placeholder="mute",
        max_length=4,
        required=True,
    )
    duration_input = discord.ui.TextInput(
        label="Тривалість (для mute): 30m, 2h, 1d, 7d",
        placeholder="2h",
        max_length=10,
        required=False,
    )

    def __init__(self, view: "WarnSetupView"):
        super().__init__()
        self.ws_view = view

    async def on_submit(self, interaction: discord.Interaction):
        count_raw = self.warn_count.value.strip()
        action = self.action_input.value.strip().lower()
        duration = self.duration_input.value.strip() or ""

        if not count_raw.isdigit() or not (1 <= int(count_raw) <= 50):
            return await interaction.response.send_message(f"{E_CROSS} Кількість має бути числом від 1 до 50.", ephemeral=True)
        if action not in ("mute", "kick", "ban"):
            return await interaction.response.send_message(f"{E_CROSS} Дія може бути: `mute`, `kick` або `ban`.", ephemeral=True)

        count = int(count_raw)
        rules = self.ws_view.settings.get("warn_escalation", [])
        rules = [r for r in rules if r["count"] != count]
        rules.append({"count": count, "action": action, "duration": duration})

        self.ws_view.settings["warn_escalation"] = rules
        await _col.update_one({"_id": interaction.guild.id}, {"$set": {"warn_escalation": rules}}, upsert=True)
        await interaction.response.edit_message(embed=_build_embed(self.ws_view.settings), view=self.ws_view)

class DeleteRuleModal(discord.ui.Modal, title="Видалити правило"):
    rule_number = discord.ui.TextInput(
        label="Номер правила для видалення",
        placeholder="1",
        max_length=2,
        required=True,
    )

    def __init__(self, view: "WarnSetupView"):
        super().__init__()
        self.ws_view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.rule_number.value.strip()
        if not raw.isdigit():
            return await interaction.response.send_message(f"{E_CROSS} Введіть номер правила.", ephemeral=True)

        idx = int(raw) - 1
        rules = sorted(self.ws_view.settings.get("warn_escalation", []), key=lambda r: r["count"])
        if idx < 0 or idx >= len(rules):
            return await interaction.response.send_message(f"{E_CROSS} Такого правила не існує.", ephemeral=True)

        rules.pop(idx)
        self.ws_view.settings["warn_escalation"] = rules
        await _col.update_one({"_id": interaction.guild.id}, {"$set": {"warn_escalation": rules}}, upsert=True)
        await interaction.response.edit_message(embed=_build_embed(self.ws_view.settings), view=self.ws_view)

class DecayModal(discord.ui.Modal, title="Спадання варнів"):
    decay_input = discord.ui.TextInput(
        label="Днів до спадання (0 = вимкнено)",
        placeholder="30",
        max_length=3,
        required=True,
    )

    def __init__(self, view: "WarnSetupView"):
        super().__init__()
        self.ws_view = view
        current = view.settings.get("warn_decay_days", 0)
        self.decay_input.default = str(current)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.decay_input.value.strip()
        if not raw.isdigit() or int(raw) > 365:
            return await interaction.response.send_message(f"{E_CROSS} Введіть число від 0 до 365.", ephemeral=True)

        days = int(raw)
        self.ws_view.settings["warn_decay_days"] = days
        await _col.update_one({"_id": interaction.guild.id}, {"$set": {"warn_decay_days": days}}, upsert=True)
        await interaction.response.edit_message(embed=_build_embed(self.ws_view.settings), view=self.ws_view)

# ── View ──────────────────────────────────────────────────────────────────────

class WarnSetupView(discord.ui.View):
    def __init__(self, settings: dict):
        super().__init__(timeout=86400)
        self.settings = settings

    @discord.ui.button(label="Додати правило", style=discord.ButtonStyle.secondary, row=0)
    async def add_rule_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddRuleModal(self))

    @discord.ui.button(label="Видалити правило", style=discord.ButtonStyle.secondary, row=0)
    async def del_rule_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        rules = self.settings.get("warn_escalation", [])
        if not rules:
            return await interaction.response.send_message(f"{E_CROSS} Немає правил для видалення.", ephemeral=True)
        await interaction.response.send_modal(DeleteRuleModal(self))

    @discord.ui.button(label="Очистити все", style=discord.ButtonStyle.danger, row=0)
    async def clear_rules_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.settings["warn_escalation"] = []
        await _col.update_one({"_id": interaction.guild.id}, {"$set": {"warn_escalation": []}}, upsert=True)
        await interaction.response.edit_message(embed=_build_embed(self.settings), view=self)

    @discord.ui.button(label="Спадання варнів", style=discord.ButtonStyle.secondary, row=1)
    async def decay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DecayModal(self))

# ── Cog ───────────────────────────────────────────────────────────────────────

class WarnSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="warn-setup", description="Налаштування системи попереджень та ескалацій")
    @app_commands.default_permissions(administrator=True)
    async def warn_setup_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await _get(interaction.guild.id)
        view = WarnSetupView(settings)
        embed = _build_embed(settings)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(WarnSetupCog(bot))
