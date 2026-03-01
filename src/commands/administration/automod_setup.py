"""
automod_setup.py — Панель налаштування Автомодерації (Smart Panel V14).
Тогли для модулів (Увімк/Вимк), білі списки каналів/ролей, кастомні слова.
"""
import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
from services.automod import reload_guild_automod_cache

db = get_database()
_col = db.guild_settings

# ── Емодзі ────────────────────────────────────────────────────────────────────
E_SETTING = "<:settings:1476196821444591768>"
E_SHIELD  = "<:shieldcheck:1477720160570839130>"
E_CROSS   = "<:krestik:1476693091355463842>"
E_CHECK   = "<:check:1454140864627740834>"

EMBED_COLOR = 0x5865F2

# Модулі автомоду з описами
MODULES = {
    "am_antispam":   {"label": "Антиспам",        "desc": "Блокує 5+ повідомлень за 5 секунд.", "emoji": "🔄"},
    "am_antiinvite": {"label": "Антизапрошення",  "desc": "Блокує посилання discord.gg.", "emoji": "🔗"},
    "am_antilink":   {"label": "Анти-посилання",  "desc": "Блокує всі URL-посилання.", "emoji": "🌐"},
    "am_caps":       {"label": "Анти-капс",       "desc": "Блокує повідомлення з 70%+ великих літер.", "emoji": "🔠"},
    "am_mentions":   {"label": "Анти-згадки",     "desc": "Блокує масові згадки (5+ пінгів).", "emoji": "📢"},
}


async def _get(guild_id: int) -> dict:
    return await _col.find_one({"_id": guild_id}) or {}

async def _set(guild_id: int, data: dict):
    await _col.update_one({"_id": guild_id}, {"$set": data}, upsert=True)


def _build_embed(settings: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"{E_SHIELD} Автомодерація",
        description="Вмикайте або вимикайте модулі кнопками нижче.",
        color=EMBED_COLOR,
    )

    for key, mod in MODULES.items():
        enabled = settings.get(key, False)
        status = f"{E_CHECK} Увімкнено" if enabled else f"{E_CROSS} Вимкнено"
        embed.add_field(
            name=f"{mod['emoji']} {mod['label']}",
            value=f"{mod['desc']}\n{status}",
            inline=True,
        )

    # Whitelist display
    wl_ch = settings.get("am_whitelist_channels", [])
    wl_roles = settings.get("am_whitelist_roles", [])
    wl_text = ""
    if wl_ch:
        wl_text += "**Канали:** " + ", ".join(f"<#{c}>" for c in wl_ch) + "\n"
    if wl_roles:
        wl_text += "**Ролі:** " + ", ".join(f"<@&{r}>" for r in wl_roles) + "\n"
    if not wl_text:
        wl_text = f"{E_CROSS} не налаштовано"
    wl_text += "\n*Адміністратори завжди ігноруються.*"

    embed.add_field(name=f"{E_SETTING} Білий список", value=wl_text, inline=False)

    # Custom words
    rules = settings.get("automod_rules", [])
    if rules:
        words = ", ".join(f"`{r['trigger']}`" for r in rules[:15])
        embed.add_field(name="🚫 Заборонені слова", value=words, inline=False)
    else:
        embed.add_field(name="🚫 Заборонені слова", value=f"{E_CROSS} не додано", inline=False)

    return embed


# ── Toggle Button ─────────────────────────────────────────────────────────────

class ToggleButton(discord.ui.Button):
    def __init__(self, key: str, label: str, enabled: bool, row: int):
        self.db_key = key
        style = discord.ButtonStyle.green if enabled else discord.ButtonStyle.gray
        emoji_str = "✅" if enabled else "❌"
        super().__init__(label=label, style=style, emoji=emoji_str, row=row)

    async def callback(self, interaction: discord.Interaction):
        view: AutomodView = self.view
        current = view.settings.get(self.db_key, False)
        new_val = not current
        view.settings[self.db_key] = new_val

        # Update button appearance
        self.style = discord.ButtonStyle.green if new_val else discord.ButtonStyle.gray
        self.emoji = "✅" if new_val else "❌"

        await _set(interaction.guild.id, {self.db_key: new_val})
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_embed(view.settings), view=view)


# ── Modals ────────────────────────────────────────────────────────────────────

class CustomWordsModal(discord.ui.Modal, title="Заборонені слова/фрази"):
    words_input = discord.ui.TextInput(
        label="Слова через кому (або залиште пустим для очищення)",
        placeholder="слово1, фраза два, тег3",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, view: "AutomodView"):
        super().__init__()
        self.am_view = view
        current = view.settings.get("automod_rules", [])
        if current:
            self.words_input.default = ", ".join(r["trigger"] for r in current)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.words_input.value.strip()
        if not raw:
            rules = []
        else:
            words = [w.strip() for w in raw.split(",") if w.strip()]
            rules = [{"trigger": w, "action": "warn", "reason": "Заборонене слово"} for w in words]

        self.am_view.settings["automod_rules"] = rules
        await _set(interaction.guild.id, {"automod_rules": rules})
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_embed(self.am_view.settings), view=self.am_view)


class WhitelistRolesModal(discord.ui.Modal, title="Білий список ролей"):
    roles_input = discord.ui.TextInput(
        label="ID ролей через кому",
        placeholder="123456789, 987654321",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, view: "AutomodView"):
        super().__init__()
        self.am_view = view
        current = view.settings.get("am_whitelist_roles", [])
        if current:
            self.roles_input.default = ", ".join(str(r) for r in current)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.roles_input.value.strip()
        if not raw:
            ids = []
        else:
            ids = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]

        self.am_view.settings["am_whitelist_roles"] = ids
        await _set(interaction.guild.id, {"am_whitelist_roles": ids})
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_embed(self.am_view.settings), view=self.am_view)


# ── Bottom buttons ────────────────────────────────────────────────────────────

class CustomWordsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Заборонені слова", style=discord.ButtonStyle.primary, emoji="🚫", row=2)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CustomWordsModal(self.view))


class WhitelistChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Білий список каналів ...",
            min_values=0,
            max_values=5,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        ids = [ch.id for ch in self.values] if self.values else []
        self.view.settings["am_whitelist_channels"] = ids
        await _set(interaction.guild.id, {"am_whitelist_channels": ids})
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_embed(self.view.settings), view=self.view)


class WhitelistRolesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Білий список ролей", style=discord.ButtonStyle.secondary, emoji="🛡️", row=4)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WhitelistRolesModal(self.view))


# ── Main View ─────────────────────────────────────────────────────────────────

class AutomodView(discord.ui.View):
    def __init__(self, settings: dict):
        super().__init__(timeout=86400)
        self.settings = settings

        # Row 0: First 3 toggle buttons
        keys = list(MODULES.keys())
        for i, key in enumerate(keys[:3]):
            mod = MODULES[key]
            enabled = settings.get(key, False)
            self.add_item(ToggleButton(key, mod["label"], enabled, row=0))

        # Row 1: Remaining 2 toggle buttons
        for key in keys[3:]:
            mod = MODULES[key]
            enabled = settings.get(key, False)
            self.add_item(ToggleButton(key, mod["label"], enabled, row=1))

        # Row 2: Custom words button
        self.add_item(CustomWordsButton())

        # Row 3: Whitelist channels
        self.add_item(WhitelistChannelSelect())

        # Row 4: Whitelist roles button
        self.add_item(WhitelistRolesButton())


# ── Cog ───────────────────────────────────────────────────────────────────────

class AutomodSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="automod", description="Налаштування автомодерації сервера")
    @app_commands.default_permissions(administrator=True)
    async def automod_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await _get(interaction.guild.id)
        view = AutomodView(settings)
        embed = _build_embed(settings)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutomodSetupCog(bot))
