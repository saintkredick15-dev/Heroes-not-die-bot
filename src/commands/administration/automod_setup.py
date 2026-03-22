"""
automod_setup.py — Панель налаштування Автомодерації (Smart Panel V14).
Головна панель з тоглами → sub-panel для кожного модуля з налаштуваннями.
"""
import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
from services.automod import reload_guild_automod_cache
from utils.ui_contract import add_section, compact_kv, set_surface_footer, surface_embed

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

DEFAULT_TRUSTED_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "tenor.com",
    "giphy.com",
    "github.com",
    "imgur.com",
]

MODULES = {
    "am_antispam":   {"label": "Антиспам",         "emoji": "<:repeat:1454136632197255220>",    "desc": "Блокує флуд повідомленнями за короткий час."},
    "am_antiinvite": {"label": "Антизапрошення",   "emoji": "<:nolink:1477753086369075281>",    "desc": "Блокує посилання discord.gg."},
    "am_antilink":   {"label": "Анти-посилання",   "emoji": "<:URL:1477753429651755150>",       "desc": "Блокує всі URL-посилання."},
    "am_caps":       {"label": "Анти-капс",        "emoji": "<:alphabet:1478023308619288626>",  "desc": "Блокує повідомлення з великою кількістю CAPS."},
    "am_mentions":   {"label": "Анти-згадки",      "emoji": "<:mention:1478023765194576026>",   "desc": "Блокує масові згадки в одному повідомленні."},
    "am_emojispam":  {"label": "Emoji-спам",       "emoji": "<:emoji:1478089741080465650>",     "desc": "Блокує повідомлення з надмірною кількістю емодзі."},
    "am_imagespam":  {"label": "Image-спам",      "emoji": "<:photo:1476690859029172456>",     "desc": "Ловить масове закидання картинок/файлів."},
}

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


def _parse_id_csv(raw: str) -> list[int]:
    if not raw.strip():
        return []
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise ValueError(f"Некоректний ID: {part}")
        values.append(int(part))
    return values


def _serialize_rule(rule: dict) -> str:
    parts = [
        rule.get("trigger", ""),
        rule.get("action", "warn"),
        rule.get("target", "both"),
        rule.get("match", "contains"),
        rule.get("reason", "Заборонене слово"),
        rule.get("response_text", ""),
        ",".join(str(x) for x in rule.get("only_channels", []) or []),
        ",".join(str(x) for x in rule.get("ignore_channels", []) or []),
        ",".join(str(x) for x in rule.get("only_roles", []) or []),
        ",".join(str(x) for x in rule.get("ignore_roles", []) or []),
        str(rule.get("log_channel_id", "") or ""),
        rule.get("mute_dur", ""),
    ]
    return " | ".join(parts)


def _rule_preview(rule: dict) -> str:
    trigger = rule.get("trigger", "rule")
    action = rule.get("action", "warn")
    target = rule.get("target", "both")
    matcher = rule.get("match", "contains")
    scope = []
    if rule.get("only_channels"):
        scope.append(f"only ch {len(rule['only_channels'])}")
    if rule.get("ignore_channels"):
        scope.append(f"ignore ch {len(rule['ignore_channels'])}")
    if rule.get("only_roles"):
        scope.append(f"only roles {len(rule['only_roles'])}")
    if rule.get("ignore_roles"):
        scope.append(f"ignore roles {len(rule['ignore_roles'])}")
    scope_text = f" [{', '.join(scope)}]" if scope else ""
    return f"`{trigger}` -> `{action}` | `{target}` | `{matcher}`{scope_text}"


def _rule_details(rule: dict) -> list[str]:
    details = [
        f"Trigger: `{rule.get('trigger', '')}`",
        f"Action: `{rule.get('action', 'warn')}`",
        f"Target: `{rule.get('target', 'both')}`",
        f"Match: `{rule.get('match', 'contains')}`",
        f"Reason: `{rule.get('reason', 'No reason')}`",
    ]
    if rule.get("response_text"):
        details.append(f"Response: `{rule['response_text']}`")
    if rule.get("log_channel_id"):
        details.append(f"Log channel: <#{rule['log_channel_id']}>")
    if rule.get("mute_dur"):
        details.append(f"Mute: `{rule['mute_dur']}`")
    if rule.get("only_channels"):
        details.append(f"Only channels: {', '.join(f'<#{item}>' for item in rule['only_channels'])}")
    if rule.get("ignore_channels"):
        details.append(f"Ignore channels: {', '.join(f'<#{item}>' for item in rule['ignore_channels'])}")
    if rule.get("only_roles"):
        details.append(f"Only roles: {', '.join(f'<@&{item}>' for item in rule['only_roles'])}")
    if rule.get("ignore_roles"):
        details.append(f"Ignore roles: {', '.join(f'<@&{item}>' for item in rule['ignore_roles'])}")
    return details


def _parse_rule_lines(raw: str) -> list[dict]:
    if not raw.strip():
        return []

    rules = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 5:
            raise ValueError("Кожне правило має містити щонайменше: trigger | action | target | match | reason")

        trigger, action, target, matcher, reason = parts[:5]
        response_text = parts[5] if len(parts) > 5 else ""
        only_channels = parts[6] if len(parts) > 6 else ""
        ignore_channels = parts[7] if len(parts) > 7 else ""
        only_roles = parts[8] if len(parts) > 8 else ""
        ignore_roles = parts[9] if len(parts) > 9 else ""
        log_channel_id = parts[10] if len(parts) > 10 else ""
        mute_dur = parts[11] if len(parts) > 11 else ""

        actions = [item.strip().lower() for item in action.split(",") if item.strip()]
        if not trigger:
            raise ValueError("Trigger не може бути порожнім.")
        if not actions or any(item not in {"warn", "mute", "delete"} for item in actions):
            raise ValueError(f"Некоректна дія для trigger `{trigger}`.")
        if target not in {"message", "profile", "both"}:
            raise ValueError(f"Некоректний target для trigger `{trigger}`.")
        if matcher not in {"contains", "exact"}:
            raise ValueError(f"Некоректний match для trigger `{trigger}`.")

        rule = {
            "trigger": trigger,
            "action": ",".join(actions),
            "target": target,
            "match": matcher,
            "reason": reason or "Заборонене слово",
        }
        if response_text:
            rule["response_text"] = response_text
        if only_channels:
            rule["only_channels"] = _parse_id_csv(only_channels)
        if ignore_channels:
            rule["ignore_channels"] = _parse_id_csv(ignore_channels)
        if only_roles:
            rule["only_roles"] = _parse_id_csv(only_roles)
        if ignore_roles:
            rule["ignore_roles"] = _parse_id_csv(ignore_roles)
        if log_channel_id:
            if not log_channel_id.isdigit():
                raise ValueError(f"Некоректний log channel id для trigger `{trigger}`.")
            rule["log_channel_id"] = int(log_channel_id)
        if mute_dur:
            rule["mute_dur"] = mute_dur
        rules.append(rule)

    return rules

# ── Embeds ────────────────────────────────────────────────────────────────────


def _status_text(enabled: bool) -> str:
    return f"{E_CHECK} Увімкнено" if enabled else f"{E_CROSS} Вимкнено"


def _preview_values(values: list, empty_text: str, limit: int = 3, formatter=str) -> str:
    if not values:
        return empty_text

    preview = ", ".join(formatter(value) for value in values[:limit])
    if len(values) > limit:
        preview += f" +{len(values) - limit}"
    return preview


def _module_snapshot(key: str, settings: dict) -> list[str]:
    if key == "am_antispam":
        return [
            f"Поріг: `{settings.get('am_antispam_count', 5)}` / `{settings.get('am_antispam_interval', 5)}с`",
            f"Дія: `{settings.get('am_antispam_action', 'warn')}`",
        ]
    if key == "am_antiinvite":
        allowed = settings.get("am_antiinvite_allowed_servers", [])
        return [
            f"Дія: `{settings.get('am_antiinvite_action', 'delete')}`",
            f"Винятки: `{len(allowed)}` серверів",
        ]
    if key == "am_antilink":
        allowed = settings.get("am_antilink_allowed_domains", [])
        return [
            f"Дія: `{settings.get('am_antilink_action', 'delete')}`",
            f"Винятки: `{len(allowed)}` доменів",
        ]
    if key == "am_caps":
        return [
            f"Поріг: `{settings.get('am_caps_percent', 70)}%` CAPS",
            f"Мін. довжина: `{settings.get('am_caps_minlen', 8)}`",
        ]
    if key == "am_mentions":
        return [
            f"Макс. згадок: `{settings.get('am_mentions_max', 5)}`",
            f"Дія: `{settings.get('am_mentions_action', 'warn')}`",
        ]
    if key == "am_emojispam":
        return [
            f"Макс. емодзі: `{settings.get('am_emojispam_max', 10)}`",
            f"Дія: `{settings.get('am_emojispam_action', 'delete')}`",
        ]
    if key == "am_imagespam":
        return [
            f"Поріг: `{settings.get('am_imagespam_count', 5)}` / `{settings.get('am_imagespam_interval', 10)}с`",
            f"Дія: `{settings.get('am_imagespam_action', 'warn')}`",
        ]
    return []

def _build_main_embed(settings: dict) -> discord.Embed:
    enabled_count = sum(1 for key in MODULES if settings.get(key, False))
    total_count = len(MODULES)
    embed = discord.Embed(
        title=f"{E_HAMMER} Автомодерація",
        description=(
            f"Активно модулів: `{enabled_count}/{total_count}`\n"
            "Верхні кнопки відкривають модулі, нижні контролі керують whitelist і кастомними правилами. `Керувати правилами` відкриває rule-by-rule editor."
        ),
        color=EMBED_COLOR,
    )
    for key, mod in MODULES.items():
        enabled = settings.get(key, False)
        details = "\n".join(_module_snapshot(key, settings))
        value = _status_text(enabled)
        if details:
            value = f"{value}\n{details}"
        embed.add_field(name=f"{mod['emoji']} {mod['label']}", value=value, inline=True)

    wl_ch = settings.get("am_whitelist_channels", [])
    wl_roles = settings.get("am_whitelist_roles", [])
    wl_text = (
        f"Канали: {_preview_values(wl_ch, f'{E_CROSS} не вибрано', formatter=lambda c: f'<#{c}>')}\n"
        f"Ролі: {_preview_values(wl_roles, f'{E_CROSS} не вибрано', formatter=lambda r: f'<@&{r}>')}\n"
        "*Адміністратори ігноруються.*"
    )
    embed.add_field(name=f"{E_SETTING} Білий список", value=wl_text, inline=False)

    rules = settings.get("automod_rules", [])
    if rules:
        words = "\n".join(_rule_preview(rule) for rule in rules[:4])
        suffix = f"\n+ ще `{len(rules) - 4}` правил" if len(rules) > 4 else ""
        embed.add_field(
            name=f"{E_NO} Кастомні правила",
            value=(
                f"Кількість: `{len(rules)}`\n"
                f"{words}{suffix}\n"
                "`trigger | action | target | match | reason | ...`"
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name=f"{E_NO} Кастомні правила",
            value=f"{E_CROSS} не додано\n`trigger | action | target | match | reason | ...`",
            inline=False,
        )
    embed.set_footer(text="Спочатку вмикайте потрібні модулі, потім додавайте винятки і кастомні правила. `/config` краще підходить для preset-ів та import/export.")
    return embed

def _build_module_embed(key: str, settings: dict) -> discord.Embed:
    mod = MODULES[key]
    enabled = settings.get(key, False)
    status = _status_text(enabled)

    embed = discord.Embed(
        title=f"{mod['emoji']} {mod['label']}",
        description=f"{mod['desc']}\nСтатус: {status}",
        color=EMBED_COLOR,
    )
    snapshot = _module_snapshot(key, settings)
    if snapshot:
        embed.add_field(name="Поточна поведінка", value="\n".join(snapshot), inline=False)

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

    rules = settings.get("automod_rules", [])
    if rules:
        profile_rules = sum(1 for rule in rules if rule.get("target", "both") in {"profile", "both"})
        message_rules = sum(1 for rule in rules if rule.get("target", "both") in {"message", "both"})
        embed.add_field(
            name="Шар кастомних правил",
            value=f"Повідомлення: `{message_rules}`\nПрофілі: `{profile_rules}`",
            inline=True,
        )

    embed.set_footer(text="Пороги й дії змінюються тут. Для rich custom rules використовуйте `Керувати правилами` або `/config` import/export.")

    return embed

# ── Modals ────────────────────────────────────────────────────────────────────

def _build_main_embed(settings: dict) -> discord.Embed:
    enabled_count = sum(1 for key in MODULES if settings.get(key, False))
    total_count = len(MODULES)
    embed = surface_embed(
        "admin",
        f"{E_HAMMER} Автомодерація",
        f"Огляд модулів: `{enabled_count}/{total_count}` активних. Верхній рівень дає summary, нижче — whitelist і rule-management.",
    )
    for key, mod in MODULES.items():
        lines = [compact_kv("Статус", _status_text(settings.get(key, False)))]
        lines.extend(_module_snapshot(key, settings))
        add_section(embed, f"{mod['emoji']} {mod['label']}", lines)

    wl_ch = settings.get("am_whitelist_channels", [])
    wl_roles = settings.get("am_whitelist_roles", [])
    add_section(
        embed,
        f"{E_SETTING} Білий список",
        [
            compact_kv("Канали", _preview_values(wl_ch, f"{E_CROSS} не вибрано", formatter=lambda c: f"<#{c}>")),
            compact_kv("Ролі", _preview_values(wl_roles, f"{E_CROSS} не вибрано", formatter=lambda r: f"<@&{r}>")),
            "Адміністратори ігноруються автоматично.",
        ],
    )

    rules = settings.get("automod_rules", [])
    if rules:
        words = "\n".join(_rule_preview(rule) for rule in rules[:4])
        suffix = f"\n+ ще `{len(rules) - 4}` правил" if len(rules) > 4 else ""
        add_section(embed, f"{E_NO} Кастомні правила", [f"Кількість: `{len(rules)}`", f"{words}{suffix}", "`trigger | action | target | match | reason | ...`"])
    else:
        add_section(embed, f"{E_NO} Кастомні правила", [f"{E_CROSS} не додано", "`trigger | action | target | match | reason | ...`"])

    set_surface_footer(embed, "admin", "Спочатку вмикай модулі, потім додавай винятки і кастомні правила. `/config` краще підходить для preset-ів та import/export.")
    return embed


def _build_module_embed(key: str, settings: dict) -> discord.Embed:
    mod = MODULES[key]
    embed = surface_embed(
        "admin",
        f"{mod['emoji']} {mod['label']}",
        f"{mod['desc']}\nСтатус: {_status_text(settings.get(key, False))}",
    )
    snapshot = _module_snapshot(key, settings)
    if snapshot:
        add_section(embed, "Поточна поведінка", snapshot)

    if key in MODULE_SETTINGS:
        detail_lines = []
        for skey, sinfo in MODULE_SETTINGS[key].items():
            if skey.endswith("_mute_dur"):
                action_key = skey.replace("_mute_dur", "_action")
                if "mute" not in str(settings.get(action_key, "")):
                    continue
            value = settings.get(skey, sinfo["default"])
            if value == "":
                value = "—"
            detail_lines.append(compact_kv(sinfo["name"], f"`{value}`"))
        if detail_lines:
            add_section(embed, "Детальні пороги", detail_lines)

    if key == "am_antispam":
        add_section(embed, "Повтори", [compact_kv("Ловити повтори", _status_text(settings.get("am_antispam_duplicates", False)))])
    elif key == "am_antiinvite":
        allowed = settings.get("am_antiinvite_allowed_servers", [])
        names = ", ".join(f"`{s.get('name', '?')}`" for s in allowed) if allowed and isinstance(allowed[0], dict) else ", ".join(f"`{s}`" for s in allowed)
        add_section(embed, "Дозволені сервери", [names or f"{E_CROSS} не вказано"])
    elif key == "am_antilink":
        allowed = settings.get("am_antilink_allowed_domains", [])
        add_section(embed, "Дозволені домени", [", ".join(f"`{d}`" for d in allowed) if allowed else f"{E_CROSS} не вказано"])

    rules = settings.get("automod_rules", [])
    if rules:
        profile_rules = sum(1 for rule in rules if rule.get("target", "both") in {"profile", "both"})
        message_rules = sum(1 for rule in rules if rule.get("target", "both") in {"message", "both"})
        add_section(embed, "Кастомний шар", [compact_kv("Повідомлення", f"`{message_rules}`"), compact_kv("Профілі", f"`{profile_rules}`")])

    set_surface_footer(embed, "admin", "Пороги й дії змінюються тут. Для rich custom rules використовуй `Керувати правилами` або `/config` import/export.")
    return embed


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

class CustomWordsModal(discord.ui.Modal, title="Кастомні правила автомоду"):
    words_input = discord.ui.TextInput(
        label="По одному правилу на рядок",
        placeholder="spam word | warn | message | contains | Advertising",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000,
    )

    def __init__(self, view):
        super().__init__()
        self.am_view = view
        current = view.settings.get("automod_rules", [])
        if current:
            self.words_input.default = "\n".join(_serialize_rule(rule) for rule in current[:15])

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.words_input.value.strip()
        try:
            rules = _parse_rule_lines(raw)
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        self.am_view.settings["automod_rules"] = rules
        await _set(interaction.guild.id, {"automod_rules": rules})
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_build_main_embed(self.am_view.settings), view=self.am_view)


def _build_rules_manager_embed(settings: dict, selected_index: int | None = None) -> discord.Embed:
    rules = settings.get("automod_rules", [])
    embed = discord.Embed(
        title="Керування кастомними правилами",
        description=f"Налаштовано правил: `{len(rules)}`",
        color=EMBED_COLOR,
    )
    if not rules:
        embed.add_field(name="Стан", value=f"{E_CROSS} Правил ще немає. Додайте одне правило або скористайтесь масовим редагуванням.", inline=False)
        embed.set_footer(text="Формат рядка: trigger | action | target | match | reason | response | only_channels | ignore_channels | only_roles | ignore_roles | log_channel_id | mute_dur")
        return embed

    preview = "\n".join(f"{index + 1}. {_rule_preview(rule)}" for index, rule in enumerate(rules[:8]))
    if len(rules) > 8:
        preview += f"\n+ `{len(rules) - 8}` ще правил"
    embed.add_field(name="Правила", value=preview, inline=False)

    if selected_index is not None and 0 <= selected_index < len(rules):
        embed.add_field(name="Вибране правило", value="\n".join(_rule_details(rules[selected_index])), inline=False)
    else:
        embed.add_field(name="Вибране правило", value="Оберіть правило нижче, щоб переглянути або відредагувати його.", inline=False)
    embed.set_footer(text="`Додати правило` створює одне правило. `Масове редагування` підходить для швидкого bulk-оновлення всього списку.")
    return embed


class SingleRuleModal(discord.ui.Modal):
    rule_input = discord.ui.TextInput(
        label="Рядок правила",
        placeholder="spam word | warn | message | contains | Advertising",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )

    def __init__(self, manager_view, rule_index: int | None):
        title = "Додати правило" if rule_index is None else "Редагувати правило"
        super().__init__(title=title)
        self.manager_view = manager_view
        self.rule_index = rule_index
        if rule_index is not None:
            rule = manager_view.settings.get("automod_rules", [])[rule_index]
            self.rule_input.default = _serialize_rule(rule)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            parsed = _parse_rule_lines(self.rule_input.value.strip())
        except ValueError as exc:
            return await interaction.response.send_message(f"{E_CROSS} {exc}", ephemeral=True)
        if len(parsed) != 1:
            return await interaction.response.send_message(f"{E_CROSS} Тут треба ввести рівно один рядок правила.", ephemeral=True)

        rules = [dict(rule) for rule in self.manager_view.settings.get("automod_rules", [])]
        if self.rule_index is None:
            rules.append(parsed[0])
        else:
            rules[self.rule_index] = parsed[0]
        self.manager_view.settings["automod_rules"] = rules
        await _set(interaction.guild.id, {"automod_rules": rules})
        await reload_guild_automod_cache(interaction.guild.id)
        new_view = RulesManagerView(self.manager_view.main_view, self.manager_view.settings, self.rule_index if self.rule_index is not None else len(rules) - 1)
        await interaction.response.edit_message(embed=_build_rules_manager_embed(self.manager_view.settings, new_view.selected_index), view=new_view)


class RulePicker(discord.ui.Select):
    def __init__(self, settings: dict, selected_index: int | None):
        options = []
        for index, rule in enumerate(settings.get("automod_rules", [])[:25]):
            options.append(
                discord.SelectOption(
                    label=f"{index + 1}. {rule.get('trigger', 'rule')}"[:100],
                    value=str(index),
                    description=f"{rule.get('action', 'warn')} | {rule.get('target', 'both')} | {rule.get('match', 'contains')}"[:100],
                    default=index == selected_index,
                )
            )
        super().__init__(placeholder="Оберіть правило для перегляду...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: RulesManagerView = self.view
        selected_index = int(self.values[0])
        new_view = RulesManagerView(view.main_view, view.settings, selected_index)
        await interaction.response.edit_message(embed=_build_rules_manager_embed(view.settings, selected_index), view=new_view)


class RuleManagerBackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Назад до автомоду", style=discord.ButtonStyle.secondary, row=2)

    async def callback(self, interaction: discord.Interaction):
        view: RulesManagerView = self.view
        await interaction.response.edit_message(embed=_build_main_embed(view.settings), view=view.main_view)


class RulesManagerView(discord.ui.View):
    def __init__(self, main_view, settings: dict, selected_index: int | None = None):
        super().__init__(timeout=1800)
        self.main_view = main_view
        self.settings = settings
        self.selected_index = selected_index

        rules = settings.get("automod_rules", [])
        if rules:
            self.add_item(RulePicker(settings, selected_index))

        self.add_item(RuleManagerBackButton())

        disabled = selected_index is None or selected_index >= len(rules)
        self.edit_btn.disabled = disabled
        self.delete_btn.disabled = disabled

    @discord.ui.button(label="Додати правило", style=discord.ButtonStyle.success, row=1)
    async def add_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SingleRuleModal(self, None))

    @discord.ui.button(label="Масове редагування", style=discord.ButtonStyle.secondary, row=1)
    async def bulk_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(CustomWordsModal(self.main_view))

    @discord.ui.button(label="Редагувати вибране", style=discord.ButtonStyle.primary, row=1)
    async def edit_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SingleRuleModal(self, self.selected_index))

    @discord.ui.button(label="Видалити вибране", style=discord.ButtonStyle.danger, row=1)
    async def delete_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message(f"{E_CROSS} Спочатку оберіть правило.", ephemeral=True)
        rules = [dict(rule) for rule in self.settings.get("automod_rules", [])]
        removed = rules.pop(self.selected_index)
        self.settings["automod_rules"] = rules
        await _set(interaction.guild.id, {"automod_rules": rules})
        await reload_guild_automod_cache(interaction.guild.id)
        new_selected = min(self.selected_index, len(rules) - 1) if rules else None
        new_view = RulesManagerView(self.main_view, self.settings, new_selected)
        await interaction.response.edit_message(embed=_build_rules_manager_embed(self.settings, new_selected), view=new_view)
        await interaction.followup.send(f"{E_CHECK} Правило `{removed.get('trigger', 'rule')}` видалено.", ephemeral=True)


class ManageRulesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Керувати правилами", style=discord.ButtonStyle.primary, emoji=discord.PartialEmoji.from_str(E_NO), row=3)

    async def callback(self, interaction: discord.Interaction):
        main_view: AutomodView = self.view
        manager_view = RulesManagerView(main_view, main_view.settings)
        await interaction.response.edit_message(embed=_build_rules_manager_embed(main_view.settings), view=manager_view)

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


class TrustedDomainsPresetButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Пресет довірених доменів", style=discord.ButtonStyle.secondary, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: ModuleSubView = self.view
        domains = DEFAULT_TRUSTED_DOMAINS.copy()
        view.settings["am_antilink_allowed_domains"] = domains
        await _set(interaction.guild.id, {"am_antilink_allowed_domains": domains})
        await reload_guild_automod_cache(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_build_module_embed(view.mod_key, view.settings),
            view=ModuleSubView(view.mod_key, view.settings),
        )

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
                
                resolved.append({"guild_id": int(entry), "name": f"ID: {entry}"})
            else:
                errors.append(entry)

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
            msg += "<:cutiecheckmark:1479120440734650389> " + ", ".join(f"**{s['name']}**" for s in unique)
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
        current = settings.get(key, False)
        self.toggle_btn.label = "Вимкнути модуль" if current else "Увімкнути модуль"
        self.toggle_btn.style = discord.ButtonStyle.danger if current else discord.ButtonStyle.success
        self.settings_btn.disabled = key not in MODULE_SETTINGS
        self.back_btn.label = "До модулів"

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
            self.add_item(TrustedDomainsPresetButton())

    @discord.ui.button(label="Увімк/Вимк", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.settings.get(self.mod_key, False)
        new_val = not current
        self.settings[self.mod_key] = new_val
        await _set(interaction.guild.id, {self.mod_key: new_val})
        await reload_guild_automod_cache(interaction.guild.id)
        button.label = "Вимкнути модуль" if new_val else "Увімкнути модуль"
        button.style = discord.ButtonStyle.danger if new_val else discord.ButtonStyle.success
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
        
        row_map = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3}
        for i, key in enumerate(keys):
            mod = MODULES[key]
            enabled = settings.get(key, False)
            self.add_item(ModuleButton(key, mod, enabled, row=row_map[i]))

        self.add_item(CustomWordsButton())
        self.add_item(WhitelistRolesButton())
        self.add_item(ManageRulesButton())
        self.add_item(WhitelistChannelSelect(settings))

class CustomWordsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Масове редагування правил",
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
