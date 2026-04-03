"""
logs_setup.py — Багаторівнева панель налаштування логів (Smart Panel V14).
"""
import discord
from discord import app_commands
from discord.ext import commands
from config.constants import Emojis as _E
from modules.db import get_database

db = get_database()
_col = db.guild_settings

# ── Емодзі ────────────────────────────────────────────────────────────────────
E_SETTING     = _E.SETTINGS.value
E_CROSS       = _E.CROSS.value
E_SHIELD      = _E.SHIELD_CHECK.value
E_CHAT        = _E.CHAT.value
E_MEMBERS     = _E.MEMBERS.value
E_VOICE       = _E.TICKET.value
E_STATS       = _E.STATS.value
E_CLOCK       = _E.CLOCK.value

# ── Категорії та їхні ключі БД ───────────────────────────────────────────────
LOG_TYPES = {
    "mod": {
        "log_mod_action": "Модераційна дія",
        "log_mod_auto": "Автоматична модерація",
    },
    "msg": {
        "log_msg_delete": "Видалення повідомлень",
        "log_msg_edit": "Редагування повідомлень",
    },
    "member": {
        "log_member_join": "Вхід учасника",
        "log_member_leave": "Вихід учасника",
    },
    "voice": {
        "log_voice_join": "Підключення до голосового",
        "log_voice_leave": "Відключення від голосового",
        "log_voice_move": "Переміщення між каналами",
    },
    "stats": {
        "stats_channel": "Канал статистики",
    }
}

CAT_DESCRIPTIONS = {
    "mod": "Логування банів, мутів, кіків та попереджень.",
    "msg": "Логування видалених та відредагованих повідомлень.",
    "member": "Логування входу та виходу учасників сервера.",
    "voice": "Логування підключень до голосових каналів.",
    "stats": "Канал та інтервал публікації серверної статистики.",
    "whitelist": "Канали та ролі, які ігноруються системою логування.",
}

CAT_NAMES = {
    "mod": f"{E_SHIELD} Модерація",
    "msg": f"{E_CHAT} Повідомлення",
    "member": f"{E_MEMBERS} Учасники",
    "voice": f"{E_VOICE} Голосові Канали",
    "stats": f"{E_STATS} Статистика",
    "whitelist": f"{E_SETTING} Білий список",
}

async def _get(guild_id: int) -> dict:
    return await _col.find_one({"_id": guild_id}) or {}

async def _set(guild_id: int, key: str, value):
    await _col.update_one({"_id": guild_id}, {"$set": {key: value}}, upsert=True)

def _ch_name(guild: discord.Guild, ch_id: int | None) -> str:
    if not ch_id:
        return f"{E_CROSS} не вказано"
    ch = guild.get_channel(ch_id)
    return f"<#{ch_id}>" if ch else f"{E_CROSS} канал не знайдено"

def _build_embed(guild: discord.Guild, settings: dict, category: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"{E_SETTING} Налаштування Логів",
        color=0x1a1a2e,
    )

    if category in LOG_TYPES:
        embed.description = CAT_DESCRIPTIONS.get(category, "")
        for key, name in LOG_TYPES[category].items():
            val = _ch_name(guild, settings.get(key))
            embed.add_field(name=name, value=val, inline=False)
        if category == "stats":
            interval = settings.get("stats_interval_days", 7)
            embed.add_field(name="Інтервал публікації", value=f"**{interval} днів**", inline=False)

    elif category == "whitelist":
        embed.description = CAT_DESCRIPTIONS["whitelist"]
        
        wl_channels = settings.get("log_whitelist_channels", [])
        if wl_channels:
            ch_list = ", ".join(f"<#{c}>" for c in wl_channels)
        else:
            ch_list = f"{E_CROSS} не вказано"
        embed.add_field(name="Канали-виключення", value=ch_list, inline=False)

        wl_roles = settings.get("log_whitelist_roles", [])
        if wl_roles:
            role_list = ", ".join(f"<@&{r}>" for r in wl_roles)
        else:
            role_list = f"{E_CROSS} не вказано"
        embed.add_field(name="Ролі-виключення", value=role_list, inline=False)

    else:
        embed.description = "Оберіть категорію логів для налаштування."

    return embed

# ── Modals ────────────────────────────────────────────────────────────────────

class IntervalModal(discord.ui.Modal, title="Інтервал статистики"):
    interval = discord.ui.TextInput(
        label="Кожні скільки днів публікувати? (1–30)",
        placeholder="7",
        max_length=2,
        required=True,
    )

    def __init__(self, view: "LogsSmartView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        val = self.interval.value.strip()
        if not val.isdigit() or not (1 <= int(val) <= 30):
            return await interaction.response.send_message(f"{E_CROSS} Введи число від 1 до 30.", ephemeral=True)
        days = int(val)
        await _set(interaction.guild.id, "stats_interval_days", days)
        self.view.settings["stats_interval_days"] = days
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings, self.view.category),
            view=self.view,
        )

class WhitelistRolesModal(discord.ui.Modal, title="Білий список ролей"):
    roles_input = discord.ui.TextInput(
        label="ID ролей через кому",
        placeholder="123456789, 987654321",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, view: "LogsSmartView"):
        super().__init__()
        self.view = view
        
        current = self.view.settings.get("log_whitelist_roles", [])
        if current:
            self.roles_input.default = ", ".join(str(r) for r in current)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.roles_input.value.strip()
        if not raw:
            ids = []
        else:
            try:
                ids = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
            except ValueError:
                return await interaction.response.send_message(f"{E_CROSS} Невірний формат. Введи ID через кому.", ephemeral=True)

        await _set(interaction.guild.id, "log_whitelist_roles", ids)
        self.view.settings["log_whitelist_roles"] = ids
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings, self.view.category),
            view=self.view,
        )

# ── Components ────────────────────────────────────────────────────────────────

class LogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, key: str, name: str, row: int, current_id: int | None = None):
        self.db_key = key
        defaults = []
        if current_id:
            defaults = [discord.Object(id=current_id)]
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Вибрати ...",
            min_values=0,
            max_values=1,
            row=row,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        ch_id = self.values[0].id if self.values else None
        await _set(interaction.guild.id, self.db_key, ch_id)
        self.view.settings[self.db_key] = ch_id
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings, self.view.category),
            view=self.view
        )

class WhitelistChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, row: int, current_ids: list[int] = None):
        defaults = [discord.Object(id=cid) for cid in (current_ids or [])]
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Вибрати ...",
            min_values=0,
            max_values=5,
            row=row,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        ids = [ch.id for ch in self.values] if self.values else []
        await _set(interaction.guild.id, "log_whitelist_channels", ids)
        self.view.settings["log_whitelist_channels"] = ids
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings, self.view.category),
            view=self.view
        )

class CategorySelect(discord.ui.Select):
    def __init__(self, current_category: str):
        options = [
            discord.SelectOption(label="Модерація", value="mod", emoji=discord.PartialEmoji.from_str(E_SHIELD), default=current_category == "mod"),
            discord.SelectOption(label="Повідомлення", value="msg", emoji=discord.PartialEmoji.from_str(E_CHAT), default=current_category == "msg"),
            discord.SelectOption(label="Учасники", value="member", emoji=discord.PartialEmoji.from_str(E_MEMBERS), default=current_category == "member"),
            discord.SelectOption(label="Голосові Канали", value="voice", emoji=discord.PartialEmoji.from_str(E_VOICE), default=current_category == "voice"),
            discord.SelectOption(label="Статистика", value="stats", emoji=discord.PartialEmoji.from_str(E_STATS), default=current_category == "stats"),
            discord.SelectOption(label="Білий список", value="whitelist", emoji=discord.PartialEmoji.from_str(E_SETTING), default=current_category == "whitelist"),
        ]
        super().__init__(placeholder="Оберіть категорію ...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        new_cat = self.values[0]
        new_view = LogsSmartView(self.view.settings, new_cat)
        await interaction.response.edit_message(
            embed=_build_embed(interaction.guild, self.view.settings, new_cat),
            view=new_view,
        )

class IntervalButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Змінити інтервал", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_CLOCK), row=2)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IntervalModal(self.view))

class WhitelistRolesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Ролі (ввести ID)", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_SHIELD), row=2)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WhitelistRolesModal(self.view))

# ── Main View ─────────────────────────────────────────────────────────────────

class LogsSmartView(discord.ui.View):
    def __init__(self, settings: dict, category: str = "main"):
        super().__init__(timeout=86400)
        self.settings = settings
        self.category = category

        self.add_item(CategorySelect(category))

        if category in LOG_TYPES:
            row = 1
            for key, name in LOG_TYPES[category].items():
                current_ch = settings.get(key)
                self.add_item(LogChannelSelect(key, name, row, current_id=current_ch))
                row += 1
                if row > 4:
                    break
            if category == "stats":
                self.add_item(IntervalButton())

        elif category == "whitelist":
            wl_ids = settings.get("log_whitelist_channels", [])
            self.add_item(WhitelistChannelSelect(row=1, current_ids=wl_ids))
            self.add_item(WhitelistRolesButton())

# ── Cog ───────────────────────────────────────────────────────────────────────

class LogsSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="logs", description="Налаштування логів сервера")
    @app_commands.default_permissions(administrator=True)
    async def logs_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await _get(interaction.guild.id)
        view = LogsSmartView(settings, "main")
        embed = _build_embed(interaction.guild, settings, "main")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(LogsSetupCog(bot))
