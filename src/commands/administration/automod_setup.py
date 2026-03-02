"""
automod_setup.py — Панель налаштування Автомодерації (Smart Panel V14).
Головна панель з тоглами → sub-panel для кожного модуля з налаштуваннями.
"""
import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
from services.automod import reload_guild_automod_cache

db = get_database()
_col = db.guild_settings

# ── Емодзі ────────────────────────────────────────────────────────────────────
E_SETTING  = "<:settings:1476196821444591768>"
E_HAMMER   = "<:hammer:1477376411642761479>"
E_CROSS    = "<:krestik:1476693091355463842>"
E_CHECK    = "<:check:1454140864627740834>"
E_NO       = "<:no:1477377225308504164>"
E_MEMBERS  = "<:members:1477720603472691420>"

EMBED_COLOR = 0x1a1a2e

# Модулі автомоду
MODULES = {
    "am_antispam":   {"label": "Антиспам",         "emoji": "<:repeat:1454136632197255220>",    "desc": "Блокує флуд повідомленнями за короткий час."},
    "am_antiinvite": {"label": "Антизапрошення",   "emoji": "<:nolink:1477753086369075281>",    "desc": "Блокує посилання discord.gg."},
    "am_antilink":   {"label": "Анти-посилання",   "emoji": "<:URL:1477753429651755150>",       "desc": "Блокує всі URL-посилання."},
    "am_caps":       {"label": "Анти-капс",        "emoji": "<:alphabet:1478023308619288626>",  "desc": "Блокує повідомлення з великою кількістю CAPS."},
    "am_mentions":   {"label": "Анти-згадки",      "emoji": "<:mention:1478023765194576026>",   "desc": "Блокує масові згадки в одному повідомленні."},
    "am_emojispam":  {"label": "Emoji-спам",       "emoji": "<:emoji:1478089741080465650>",     "desc": "Блокує повідомлення з надмірною кількістю емодзі."},
    "am_imagespam":  {"label": "Image-спам",      "emoji": "<:photo:1476690859029172456>",     "desc": "Ловить масове закидання картинок/файлів."},
}

# Налаштування модулів (label max 45 chars!)
MODULE_SETTINGS = {
    "am_antispam": {
        "am_antispam_count":    {"name": "Скільки повідомлень = спам",   "default": 5},
        "am_antispam_interval": {"name": "За скільки секунд",           "default": 5},
        "am_antispam_action":   {"name": "Дія (warn,mute,delete)",      "default": "warn"},
        "am_antispam_mute_dur": {"name": "Тривалість муту (10m/1h/1d)", "default": ""},
    },
    "am_antiinvite": {
        "am_antiinvite_action":   {"name": "Дія (warn,mute,delete)",      "default": "delete"},
        "am_antiinvite_mute_dur": {"name": "Тривалість муту (10m/1h/1d)", "default": ""},
    },
    "am_antilink": {
        "am_antilink_action":   {"name": "Дія (warn,mute,delete)",      "default": "delete"},
        "am_antilink_mute_dur": {"name": "Тривалість муту (10m/1h/1d)", "default": ""},
    },
    "am_caps": {
        "am_caps_percent":  {"name": "Поріг капсу у %",              "default": 70},
        "am_caps_minlen":   {"name": "Мін. довжина повідомлення",    "default": 8},
        "am_caps_action":   {"name": "Дія (warn,mute,delete)",       "default": "delete"},
        "am_caps_mute_dur": {"name": "Тривалість муту (10m/1h/1d)",  "default": ""},
    },
    "am_mentions": {
        "am_mentions_max":      {"name": "Макс. згадок в повідомленні", "default": 5},
        "am_mentions_action":   {"name": "Дія (warn,mute,delete)",      "default": "warn"},
        "am_mentions_mute_dur": {"name": "Тривалість муту (10m/1h/1d)", "default": ""},
    },
    "am_emojispam": {
        "am_emojispam_max":      {"name": "Макс. емодзі в повідомленні", "default": 10},
        "am_emojispam_action":   {"name": "Дія (warn,mute,delete)",       "default": "delete"},
        "am_emojispam_mute_dur": {"name": "Тривалість муту (10m/1h/1d)",  "default": ""},
    },
    "am_imagespam": {
        "am_imagespam_count":    {"name": "Скільки файлів = спам",       "default": 5},
        "am_imagespam_interval": {"name": "За скільки секунд",          "default": 10},
        "am_imagespam_action":   {"name": "Дія (warn,mute,delete)",       "default": "warn"},
        "am_imagespam_mute_dur": {"name": "Тривалість муту (10m/1h/1d)",  "default": ""},
    },
}


async def _get(guild_id: int) -> dict:
    return await _col.find_one({"_id": guild_id}) or {}

async def _set(guild_id: int, data: dict):
    await _col.update_one({"_id": guild_id}, {"$set": data}, upsert=True)


# ── Embeds ────────────────────────────────────────────────────────────────────

def _build_main_embed(settings: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"{E_HAMMER} Автомодерація",
        description="Натисніть на модуль для налаштування.",
        color=EMBED_COLOR,
    )
    for key, mod in MODULES.items():
        enabled = settings.get(key, False)
        status = f"{E_CHECK} Увімкнено" if enabled else f"{E_CROSS} Вимкнено"
        embed.add_field(name=f"{mod['emoji']} {mod['label']}", value=status, inline=True)

    # Whitelist
    wl_ch = settings.get("am_whitelist_channels", [])
    wl_roles = settings.get("am_whitelist_roles", [])
    wl_text = ""
    if wl_ch:
        wl_text += "**Канали:** " + ", ".join(f"<#{c}>" for c in wl_ch) + "\n"
    if wl_roles:
        wl_text += "**Ролі:** " + ", ".join(f"<@&{r}>" for r in wl_roles) + "\n"
    if not wl_text:
        wl_text = f"{E_CROSS} не налаштовано"
    wl_text += "\n*Адміністратори ігноруються.*"
    embed.add_field(name=f"{E_SETTING} Білий список", value=wl_text, inline=False)

    # Custom words
    rules = settings.get("automod_rules", [])
    if rules:
        words = ", ".join(f"`{r['trigger']}`" for r in rules[:15])
        embed.add_field(name=f"{E_NO} Заборонені слова", value=words, inline=False)
    else:
        embed.add_field(name=f"{E_NO} Заборонені слова", value=f"{E_CROSS} не додано", inline=False)
    return embed


def _build_module_embed(key: str, settings: dict) -> discord.Embed:
    mod = MODULES[key]
    enabled = settings.get(key, False)
    status = f"{E_CHECK} Увімкнено" if enabled else f"{E_CROSS} Вимкнено"

    embed = discord.Embed(
        title=f"{mod['emoji']} {mod['label']}",
        description=f"{mod['desc']}\nСтатус: {status}",
        color=EMBED_COLOR,
    )

    # Параметри модуля
    if key in MODULE_SETTINGS:
        for skey, sinfo in MODULE_SETTINGS[key].items():
            if skey.endswith("_mute_dur"):
                action_key = skey.replace("_mute_dur", "_action")
                if settings.get(action_key, "") != "mute":
                    continue
            val = settings.get(skey, sinfo["default"])
            if val == "":
                val = "—"
            embed.add_field(name=sinfo["name"], value=f"`{val}`", inline=True)

    # Додаткова інфо для конкретних модулів
    if key == "am_antispam":
        dup = settings.get("am_antispam_duplicates", False)
        dup_status = f"{E_CHECK} Увімкнено" if dup else f"{E_CROSS} Вимкнено"
        embed.add_field(name="Ловити повтори", value=dup_status, inline=True)

    elif key == "am_antiinvite":
        allowed = settings.get("am_antiinvite_allowed_servers", [])
        if allowed:
            if isinstance(allowed[0], dict):
                names = ", ".join(f"`{s.get('name', '?')}`" for s in allowed)
            else:
                names = ", ".join(f"`{s}`" for s in allowed)
            embed.add_field(name="Дозволені сервери", value=names, inline=False)
        else:
            embed.add_field(name="Дозволені сервери", value=f"{E_CROSS} не вказано", inline=False)

    elif key == "am_antilink":
        allowed = settings.get("am_antilink_allowed_domains", [])
        if allowed:
            embed.add_field(name="Дозволені домени", value=", ".join(f"`{d}`" for d in allowed), inline=False)
        else:
            embed.add_field(name="Дозволені домени", value=f"{E_CROSS} не вказано", inline=False)

    return embed


# ── Modals ────────────────────────────────────────────────────────────────────

class ModuleSettingsModal(discord.ui.Modal):
    def __init__(self, key: str, settings: dict, parent_view):
        mod = MODULES[key]
        super().__init__(title=f"{mod['label']}")
        self.mod_key = key
        self.parent_view = parent_view
        self.fields_map = {}

        if key not in MODULE_SETTINGS:
            return

        for skey, sinfo in MODULE_SETTINGS[key].items():
            current = str(settings.get(skey, sinfo["default"]))
            inp = discord.ui.TextInput(
                label=sinfo["name"][:45],
                placeholder=str(sinfo["default"]) if sinfo["default"] != "" else "залиште пустим",
                default=current if current else None,
                max_length=20,
                required=not skey.endswith("_mute_dur"),
            )
            self.add_item(inp)
            self.fields_map[skey] = (inp, sinfo)

    async def on_submit(self, interaction: discord.Interaction):
        update = {}
        for skey, (inp, sinfo) in self.fields_map.items():
            raw = inp.value.strip()
            if skey.endswith("_action"):
                actions = [a.strip().lower() for a in raw.split(",") if a.strip()]
                valid = {"warn", "mute", "delete"}
                if not actions or not all(a in valid for a in actions):
                    return await interaction.response.send_message(
                        f"{E_CROSS} Дія: warn, mute, delete (можна через кому: delete,warn)", ephemeral=True)
                update[skey] = ",".join(actions)
            elif skey.endswith("_mute_dur"):
                update[skey] = raw
            else:
                if not raw.isdigit():
                    return await interaction.response.send_message(
                        f"{E_CROSS} Має бути числом.", ephemeral=True)
                update[skey] = int(raw)

        self.parent_view.settings.update(update)
        await _set(interaction.guild.id, update)
        await reload_guild_automod_cache(interaction.guild.id)
        embed = _build_module_embed(self.mod_key, self.parent_view.settings)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class CustomWordsModal(discord.ui.Modal, title="Заборонені слова/фрази"):
    words_input = discord.ui.TextInput(
        label="Слова через кому",
        placeholder="слово1, фраза два (пусто = очистити)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, view):
        super().__init__()
        self.am_view = view
        current = view.settings.get("automod_rules", [])
        if current:
            self.words_input.default = ", ".join(r["trigger"] for r in current)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.words_input.value.strip()
        rules = [{"trigger": w.strip(), "action": "warn", "reason": "Заборонене слово"}
                 for w in raw.split(",") if w.strip()] if raw else []
        self.am_view.settings["automod_rules"] = rules
        await _set(interaction.guild.id, {"automod_rules": rules})
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_build_main_embed(self.am_view.settings), view=self.am_view)


class WhitelistRolesModal(discord.ui.Modal, title="Білий список ролей"):
    roles_input = discord.ui.TextInput(
        label="ID ролей через кому",
        placeholder="123456789, 987654321",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, view):
        super().__init__()
        self.am_view = view
        current = view.settings.get("am_whitelist_roles", [])
        if current:
            self.roles_input.default = ", ".join(str(r) for r in current)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.roles_input.value.strip()
        ids = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()] if raw else []
        self.am_view.settings["am_whitelist_roles"] = ids
        await _set(interaction.guild.id, {"am_whitelist_roles": ids})
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_build_main_embed(self.am_view.settings), view=self.am_view)


class AllowedDomainsModal(discord.ui.Modal, title="Дозволені домени"):
    domains_input = discord.ui.TextInput(
        label="Домени через кому",
        placeholder="youtube.com, twitch.tv, twitter.com",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, view):
        super().__init__()
        self.sub_view = view
        current = view.settings.get("am_antilink_allowed_domains", [])
        if current:
            self.domains_input.default = ", ".join(current)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.domains_input.value.strip()
        domains = [d.strip().lower() for d in raw.split(",") if d.strip()] if raw else []
        self.sub_view.settings["am_antilink_allowed_domains"] = domains
        await _set(interaction.guild.id, {"am_antilink_allowed_domains": domains})
        await reload_guild_automod_cache(interaction.guild.id)
        embed = _build_module_embed(self.sub_view.mod_key, self.sub_view.settings)
        await interaction.response.edit_message(embed=embed, view=self.sub_view)


class AllowedServersModal(discord.ui.Modal, title="Дозволені сервери"):
    servers_input = discord.ui.TextInput(
        label="Invite або ID серверів, через кому",
        placeholder="discord.gg/abc, 123456789, discord.gg/xyz",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, view):
        super().__init__()
        self.sub_view = view
        current = view.settings.get("am_antiinvite_allowed_servers", [])
        if current:
            # Показуємо назви серверів для зручності
            if isinstance(current[0], dict):
                self.servers_input.default = ", ".join(s.get("name", str(s.get("guild_id", ""))) for s in current)
            else:
                self.servers_input.default = ", ".join(str(s) for s in current)

    async def on_submit(self, interaction: discord.Interaction):
        import re
        raw = self.servers_input.value.strip()
        if not raw:
            self.sub_view.settings["am_antiinvite_allowed_servers"] = []
            await _set(interaction.guild.id, {"am_antiinvite_allowed_servers": []})
            await reload_guild_automod_cache(interaction.guild.id)
            embed = _build_module_embed(self.sub_view.mod_key, self.sub_view.settings)
            return await interaction.response.edit_message(embed=embed, view=self.sub_view)

        await interaction.response.defer(ephemeral=True)

        entries = [e.strip() for e in raw.split(",") if e.strip()]
        resolved = []
        errors = []

        invite_re = re.compile(r'(?:discord\.gg|discord\.com/invite|discordapp\.com/invite|dsc\.gg)/([a-zA-Z0-9\-]+)', re.I)

        for entry in entries:
            # Спробуємо витягти invite-код з URL
            m = invite_re.search(entry)
            code = m.group(1) if m else None

            if code:
                try:
                    invite = await interaction.client.fetch_invite(code)
                    if invite.guild:
                        resolved.append({"guild_id": invite.guild.id, "name": invite.guild.name})
                    else:
                        errors.append(entry)
                except (discord.NotFound, discord.HTTPException):
                    errors.append(entry)
            elif entry.isdigit():
                # Guild ID напряму
                resolved.append({"guild_id": int(entry), "name": f"ID: {entry}"})
            else:
                errors.append(entry)

        # Дедуплікація по guild_id
        seen = set()
        unique = []
        for s in resolved:
            if s["guild_id"] not in seen:
                seen.add(s["guild_id"])
                unique.append(s)

        self.sub_view.settings["am_antiinvite_allowed_servers"] = unique
        await _set(interaction.guild.id, {"am_antiinvite_allowed_servers": unique})
        await reload_guild_automod_cache(interaction.guild.id)

        embed = _build_module_embed(self.sub_view.mod_key, self.sub_view.settings)

        msg = ""
        if unique:
            msg += "✅ " + ", ".join(f"**{s['name']}**" for s in unique)
        if errors:
            msg += f"\n{E_CROSS} Не вдалось розпізнати: " + ", ".join(f"`{e}`" for e in errors)

        await interaction.followup.edit_message(
            interaction.message.id, embed=embed, view=self.sub_view)
        if msg:
            await interaction.followup.send(msg, ephemeral=True)


# ── Module Sub-Panel View ────────────────────────────────────────────────────

class ModuleSubView(discord.ui.View):
    def __init__(self, key: str, settings: dict):
        super().__init__(timeout=86400)
        self.mod_key = key
        self.settings = settings

        # Додаткові кнопки для конкретних модулів (row=1)
        if key == "am_antispam":
            dup_on = settings.get("am_antispam_duplicates", False)
            label = "Повтори: ВКЛ" if dup_on else "Повтори: ВИКЛ"
            style = discord.ButtonStyle.green if dup_on else discord.ButtonStyle.gray
            btn = discord.ui.Button(label=label, style=style, row=1)
            btn.callback = self._toggle_duplicates
            self.add_item(btn)

        elif key == "am_antiinvite":
            btn = discord.ui.Button(label="Дозволені сервери", style=discord.ButtonStyle.secondary, row=1)
            btn.callback = self._open_allowed_servers
            self.add_item(btn)

        elif key == "am_antilink":
            btn = discord.ui.Button(label="Дозволені домени", style=discord.ButtonStyle.secondary, row=1)
            btn.callback = self._open_allowed_domains
            self.add_item(btn)

    @discord.ui.button(label="Увімк/Вимк", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.settings.get(self.mod_key, False)
        new_val = not current
        self.settings[self.mod_key] = new_val
        await _set(interaction.guild.id, {self.mod_key: new_val})
        await reload_guild_automod_cache(interaction.guild.id)
        embed = _build_module_embed(self.mod_key, self.settings)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Змінити параметри", style=discord.ButtonStyle.secondary, row=0)
    async def settings_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.mod_key not in MODULE_SETTINGS:
            return await interaction.response.send_message(
                f"{E_CROSS} Немає параметрів.", ephemeral=True)
        await interaction.response.send_modal(
            ModuleSettingsModal(self.mod_key, self.settings, self))

    @discord.ui.button(label="← Назад", style=discord.ButtonStyle.primary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AutomodView(self.settings)
        embed = _build_main_embed(self.settings)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _toggle_duplicates(self, interaction: discord.Interaction):
        current = self.settings.get("am_antispam_duplicates", False)
        new_val = not current
        self.settings["am_antispam_duplicates"] = new_val
        await _set(interaction.guild.id, {"am_antispam_duplicates": new_val})
        await reload_guild_automod_cache(interaction.guild.id)
        new_view = ModuleSubView(self.mod_key, self.settings)
        embed = _build_module_embed(self.mod_key, self.settings)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _open_allowed_domains(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AllowedDomainsModal(self))

    async def _open_allowed_servers(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AllowedServersModal(self))


# ── Main View ─────────────────────────────────────────────────────────────────

class ModuleButton(discord.ui.Button):
    def __init__(self, key: str, mod: dict, enabled: bool, row: int):
        self.mod_key = key
        emoji = discord.PartialEmoji.from_str(mod["emoji"]) if mod["emoji"].startswith("<") else mod["emoji"]
        style = discord.ButtonStyle.green if enabled else discord.ButtonStyle.gray
        super().__init__(label=mod["label"], style=style, emoji=emoji, row=row)

    async def callback(self, interaction: discord.Interaction):
        view: AutomodView = self.view
        sub_view = ModuleSubView(self.mod_key, view.settings)
        embed = _build_module_embed(self.mod_key, view.settings)
        await interaction.response.edit_message(embed=embed, view=sub_view)


class AutomodView(discord.ui.View):
    def __init__(self, settings: dict):
        super().__init__(timeout=86400)
        self.settings = settings

        keys = list(MODULES.keys())
        # Row 0: Антиспам, Антизапрошення
        # Row 1: Анти-посилання, Анти-капс
        # Row 2: Анти-згадки, Emoji-спам
        # Row 3: Image-спам, Заборонені слова, Білий список ролей
        row_map = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3}
        for i, key in enumerate(keys):
            mod = MODULES[key]
            enabled = settings.get(key, False)
            self.add_item(ModuleButton(key, mod, enabled, row=row_map[i]))

        self.add_item(CustomWordsButton())
        self.add_item(WhitelistRolesButton())
        self.add_item(WhitelistChannelSelect(settings))


class CustomWordsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Заборонені слова",
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji.from_str(E_NO),
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CustomWordsModal(self.view))


class WhitelistChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, settings: dict):
        current_ids = settings.get("am_whitelist_channels", [])
        defaults = [discord.Object(id=cid) for cid in current_ids]
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Білий список каналів ...",
            min_values=0, max_values=5, row=4,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        ids = [ch.id for ch in self.values] if self.values else []
        self.view.settings["am_whitelist_channels"] = ids
        await _set(interaction.guild.id, {"am_whitelist_channels": ids})
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_build_main_embed(self.view.settings), view=self.view)


class WhitelistRolesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Білий список ролей",
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji.from_str(E_MEMBERS),
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WhitelistRolesModal(self.view))


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
        embed = _build_main_embed(settings)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutomodSetupCog(bot))
