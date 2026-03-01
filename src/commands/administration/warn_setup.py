"""
warn_setup.py — Панель налаштування ескалації попереджень (Smart Panel V14).
Налаштування: скільки варнів → яка дія (mute/kick/ban) та тривалість.
"""
import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database

db = get_database()
_col = db.guild_settings

# ── Емодзі ────────────────────────────────────────────────────────────────────
E_SHIELD  = "<:shieldcheck:1477720160570839130>"
E_CROSS   = "<:krestik:1476693091355463842>"
E_SETTING = "<:settings:1476196821444591768>"

EMBED_COLOR = 0x5865F2

ACTION_LABELS = {
    "mute": "🔇 Мут",
    "kick": "👢 Кік",
    "ban": "🔨 Бан",
}


async def _get(guild_id: int) -> dict:
    return await _col.find_one({"_id": guild_id}) or {}


def _build_embed(settings: dict) -> discord.Embed:
    rules = settings.get("warn_escalation", [])

    embed = discord.Embed(
        title=f"{E_SHIELD} Налаштування Попереджень",
        description="Визначте, що відбувається при накопиченні певної кількості попереджень.",
        color=EMBED_COLOR,
    )

    if not rules:
        embed.add_field(
            name="Правила ескалації",
            value=f"{E_CROSS} Не налаштовано. Натисніть **Додати правило** нижче.",
            inline=False,
        )
    else:
        # Sort by warn count
        sorted_rules = sorted(rules, key=lambda r: r["count"])
        lines = []
        for r in sorted_rules:
            action_label = ACTION_LABELS.get(r["action"], r["action"])
            duration = r.get("duration", "")
            if duration:
                lines.append(f"**{r['count']}** варнів → {action_label} на **{duration}**")
            else:
                lines.append(f"**{r['count']}** варнів → {action_label}")
        embed.add_field(name="Правила ескалації", value="\n".join(lines), inline=False)

    return embed


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

        # Remove existing rule for same count (overwrite)
        rules = [r for r in rules if r["count"] != count]
        rules.append({"count": count, "action": action, "duration": duration})

        self.ws_view.settings["warn_escalation"] = rules
        await _col.update_one(
            {"_id": interaction.guild.id},
            {"$set": {"warn_escalation": rules}},
            upsert=True,
        )
        await interaction.response.edit_message(
            embed=_build_embed(self.ws_view.settings), view=self.ws_view,
        )


class WarnSetupView(discord.ui.View):
    def __init__(self, settings: dict):
        super().__init__(timeout=86400)
        self.settings = settings

    @discord.ui.button(label="Додати правило", style=discord.ButtonStyle.primary, emoji="➕", row=0)
    async def add_rule_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddRuleModal(self))

    @discord.ui.button(label="Очистити всі правила", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def clear_rules_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.settings["warn_escalation"] = []
        await _col.update_one(
            {"_id": interaction.guild.id},
            {"$set": {"warn_escalation": []}},
            upsert=True,
        )
        await interaction.response.edit_message(
            embed=_build_embed(self.settings), view=self,
        )


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
