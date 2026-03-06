"""
/economy_setup — Адмін-панель налаштувань економіки.
Повністю кнопковий UI, без монолітних форм.
"""
import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database

db = get_database()

# ── Кастомні емодзі ───────────────────────────────────────────────────────────
E_CHECK   = "<:cutiecheckmark:1479120440734650389>"
E_CROSS   = "<:krestik:1476693091355463842>"
E_WARN    = "<:warn:1477376152191373504>"
E_CLOCK   = "<:clock:1476209087804084328>"
E_SETTING = "<:settings:1476196821444591768>"
E_COIN    = "<:coin:1478487028105482485>"
E_CHAT    = "<:chat:1475953787687403716>"
E_MICRO   = "<:micro:1475954046350135346>"
E_STAR    = "<:reactionstar:1475954213455532067>"
E_WORK    = "<:work:1478489752020975626>"
E_WORKS   = "<:works:1478510456971857992>"
E_DAILY   = "<:daily:1478510858027143289>"
E_BANK    = "<:bank:1478483868867891261>"
E_ROB     = "<:robbery:1478496325887725814>"
E_INCOME  = "<:income:1478491102788190395>"
E_RANDOM  = "<:random:1478513015002501200>"
E_SHIELD  = "<:shield:1478800925664612372>"
E_FLAME   = "<:flame:1478490474145906800>"
E_BOOST   = "<:boost:1478073594247643377>"
E_HISTORY = "<:historylist:1478824658332684510>"
E_LEFT    = "<:totheleft:1478825190749110323>"
E_STATS   = "<:statistics:1477721796857041067>"
E_CRIME   = "<:crime:1479221667468152882>"
E_SHOP    = "<:newshop:1479222868377337896>"
E_GAME    = "<:statistics:1477721796857041067>"

EMBED_COLOR = 0x1a1a2e

DEFAULT_ECO = {
    "enabled": True,
    "currency_emoji": "<:coin:1478487028105482485>",
    "currency_name": "Coin",

    "msg_earn": [5, 10],
    "msg_cooldown": 60,
    "voice_earn": 3,
    "reaction_earn": 2,

    "work_min": 100,
    "work_max": 500,
    "work_cooldown": 14400,
    "work_type": "both",
    "event_chance": 40,
    "event_stake_percent": 50,
    "event_timer": 15,

    "daily_amount": 200,
    "daily_streak_bonus": 50,
    "daily_cooldown": 86400,
    "captcha_enabled": False,

    "crime_enabled": True,
    "crime_cooldown": 28800,
    "crime_ban_duration": 1800,

    "gambling_enabled": False,
    "gambling_max_bet": 10000,
    "gambling_daily_cap": 0,
    "duel_timer": 15,
    "duel_max_rounds": 9,
    "duel_draw_refund": True,
    "casino_rtp": 95,

    "bank_base_limit": 10000,
    "bank_level_multiplier": 1000,
    "bank_interest_rate": 0.0,
    "bank_interest_interval": "daily",

    "transfer_tax_percent": 0,
    "transfer_daily_limit": 0,

    "rob_enabled": True,
    "rob_chance": 40,
    "rob_fine_percent": 25,
    "rob_min_balance_percent": 20,
    "rob_time": 10,
    "rob_cooldown": 3600,
    "rob_percent_min": 10,
    "rob_percent_max": 40,

    "shop_shield_price": 5000,
    "shop_xp_boost_price": 2000,
    "shop_lottery_price": 500,
    "shop_crime_pass_price": 3000,
    "coin_boost_duration": 86400,
    "shop_roles": [],
    "salary_roles": [],

    "quests_enabled": True,
    "quests_daily_count": 3,
    "quests_weekly_count": 2,
    "quests_daily_reward": 200,
    "quests_weekly_reward": 800,
    "quests_target_multiplier": 50,

    "season_enabled": False,
    "season_duration_days": 30,
    "season_winner_role_id": 0,
    "season_start_bonus": 0,
    "season_start": 0,
    "season_history": [],

    "duel_enabled": True,
    "work_complex_stages": 3,

    "enabled_minigames": ["math", "higher_lower", "shell", "dice", "odd_emoji", "unscramble", "trivia", "typing", "guess", "reaction"],
}

def parse_duration(value: str) -> int:
    """
    Парсить рядок в секунди.
    Підтримує англійські h/m/s та українські г/хв/с.
    Приклади: '4h', '30m', '1h30m', '8г', '30хв', '3600', '30s'
    """
    import re
    v = value.strip().lower()
    
    v = re.sub(r'(хв|хвил?)', 'm', v)  
    v = re.sub(r'г', 'h', v)              
    v = re.sub(r'с(?!\d)', 's', v)        
    
    pattern = re.compile(r'^(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?$')
    match = pattern.fullmatch(v)
    if match and any(match.group(g) for g in ('h', 'm', 's')):
        h = int(match.group('h') or 0)
        m = int(match.group('m') or 0)
        s = int(match.group('s') or 0)
        total = h * 3600 + m * 60 + s
        if total <= 0:
            raise ValueError("Duration must be > 0")
        return total
    
    return int(float(v))

def fmt_duration_modal(seconds: int) -> str:
    """Для default значень в модалах — повертає '8h', '30m', '1h30m'."""
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    s = rem % 60
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    return "".join(parts) or "0s"

def fmt_duration(seconds: int) -> str:
    """Форматує секунди → '4г', '1г 30хв', '45хв'."""
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h and m:
        return f"{h}г {m}хв"
    if h:
        return f"{h}г"
    return f"{m}хв"

def get_eco(settings: dict) -> dict:
    return {**DEFAULT_ECO, **settings.get("economy", {})}

async def save_eco(guild_id: int, updates: dict):
    await db.guild_settings.update_one(
        {"_id": guild_id}, {"$set": updates}, upsert=True
    )

# ── Embed головного меню ──────────────────────────────────────────────────────

def build_main_embed(eco: dict) -> discord.Embed:
    curr = eco["currency_emoji"]
    enabled_str = f"{E_CHECK} Увімкнена" if eco["enabled"] else f"{E_CROSS} Вимкнена"

    embed = discord.Embed(
        title=f"{E_SETTING} Налаштування Економіки",
        color=EMBED_COLOR
    )

    msg_earn = eco["msg_earn"]
    msg_str = f"{msg_earn[0]}–{msg_earn[1]}" if isinstance(msg_earn, list) else str(msg_earn)

    work_modes = {"simple": "Лише Легка", "complex": "Лише Складна", "both": "Обидва режими"}

    embed.add_field(
        name=f"{E_SETTING} Загальне",
        value=(
            f"Статус: {enabled_str}\n"
            f"Валюта: {curr} `{eco['currency_name']}`"
        ),
        inline=True
    )
    embed.add_field(
        name=f"{E_INCOME} Пасивний дохід",
        value=(
            f"{E_CHAT} Чат: `{msg_str}` {curr}  КД: `{eco['msg_cooldown']}с`\n"
            f"{E_MICRO} Войс: `{eco['voice_earn']}` {curr}/хв\n"
            f"{E_STAR} Реакції: `{eco['reaction_earn']}` {curr}"
        ),
        inline=True
    )
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(
        name=f"{E_WORK} Робота",
        value=(
            f"Сума: `{eco['work_min']}–{eco['work_max']}` {curr}\n"
            f"КД: `{fmt_duration(eco['work_cooldown'])}`\n"
            f"Режим: `{work_modes.get(eco['work_type'], 'Обидва')}`\n"
            f"Шанс події: `{eco['event_chance']}%`  Ставка: `{eco['event_stake_percent']}%`"
        ),
        inline=True
    )
    embed.add_field(
        name=f"{E_DAILY} Daily",
        value=(
            f"Сума: `{eco['daily_amount']}` {curr}\n"
            f"Стрік-бонус: `+{eco['daily_streak_bonus']}` {curr}\n"
            f"КД: `{fmt_duration(eco['daily_cooldown'])}`\n"
            f"Captcha: {E_CHECK if eco['captcha_enabled'] else E_CROSS}"
        ),
        inline=True
    )
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(
        name=f"{E_ROB} Пограбування",
        value=(
            f"Статус: {E_CHECK if eco['rob_enabled'] else E_CROSS}\n"
            f"Шанс: `{eco['rob_chance']}%`  Штраф: `{eco['rob_fine_percent']}%`\n"
            f"Мін. баланс: `{eco['rob_min_balance_percent']}%`"
        ),
        inline=True
    )
    embed.add_field(
        name=f"{E_CRIME} Крайм",
        value=(
            f"Статус: {E_CHECK if eco['crime_enabled'] else E_CROSS}\n"
            f"КД: `{fmt_duration(eco['crime_cooldown'])}`\n"
            f"Бан-штраф: `{fmt_duration(eco['crime_ban_duration'])}`"
        ),
        inline=True
    )
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(
        name=f"{E_BANK} Банк",
        value=(
            f"Базовий ліміт: `{eco['bank_base_limit']:,}` {curr}\n"
            f"Множник рівня: `+{eco['bank_level_multiplier']:,}`"
        ),
        inline=True
    )
    embed.add_field(
        name=f"{E_STATS} Гемблінг",
        value=(
            f"Статус: {E_CHECK if eco['gambling_enabled'] else E_CROSS}\n"
            f"Макс. ставка: `{eco['gambling_max_bet']:,}` {curr}"
        ),
        inline=True
    )
    embed.set_footer(text="Оберіть категорію нижче для редагування")
    return embed

# ── Embed підкатегорій ────────────────────────────────────────────────────────

def build_category_embed(eco: dict, category: str) -> discord.Embed:
    curr = eco["currency_emoji"]
    titles = {
        "general":  f"{E_SETTING} Загальне",
        "passive":  f"{E_INCOME} Пасивний дохід",
        "work":     f"{E_WORK} Робота",
        "daily":    f"{E_DAILY} Daily",
        "bank":     f"{E_BANK} Банк",
        "rob":      f"{E_ROB} Пограбування",
        "crime":    f"{E_CRIME} Крайм",
        "gambling": f"{E_STATS} Гемблінг",
        "shop":     f"{E_SHOP} Магазин",
        "games":    f"{E_GAME} Налаштування ігор",
    }
    embed = discord.Embed(
        title=titles.get(category, "Налаштування"),
        color=EMBED_COLOR
    )

    if category == "general":
        status_str = f"{E_CHECK} Увімкнена" if eco["enabled"] else f"{E_CROSS} Вимкнена"
        embed.description = (
            f"**Статус економіки:** {status_str}\n"
            f"**Валюта:** {curr} `{eco['currency_name']}`\n\n"
            f"*Використовуйте кнопки нижче для зміни.*"
        )
    elif category == "passive":
        msg_earn = eco["msg_earn"]
        msg_str = f"{msg_earn[0]}–{msg_earn[1]}" if isinstance(msg_earn, list) else str(msg_earn)
        embed.description = (
            f"{E_CHAT} **Чат:** `{msg_str}` {curr}  |  КД: `{eco['msg_cooldown']}с`\n"
            f"{E_MICRO} **Войс:** `{eco['voice_earn']}` {curr}/хв\n"
            f"{E_STAR} **Реакції:** `{eco['reaction_earn']}` {curr}"
        )
    elif category == "work":
        work_modes = {"simple": "Лише Легка", "complex": "Лише Складна", "both": "Обидва"}
        embed.description = (
            f"<:Coins:1478486725113286899> **Сума:** `{eco['work_min']}–{eco['work_max']}` {curr}\n"
            f"{E_CLOCK} **КД:** `{fmt_duration(eco['work_cooldown'])}`\n"
            f"**Режим:** `{work_modes.get(eco['work_type'], 'Обидва')}`\n"
            f"{E_RANDOM} **Шанс події:** `{eco['event_chance']}%`  |  Ставка: `{eco['event_stake_percent']}%`\n"
            f"**Таймер події:** `{eco['event_timer']}с`\n"
            f"**Етапів у складній:** `{eco.get('work_complex_stages', 3)}` шт"
        )
    elif category == "daily":
        embed.description = (
            f"<:coins:1477376020318388274> **Сума:** `{eco['daily_amount']}` {curr}\n"
            f"{E_FLAME} **Стрік-бонус:** `+{eco['daily_streak_bonus']}` {curr}/день\n"
            f"{E_CLOCK} **КД:** `{fmt_duration(eco['daily_cooldown'])}`\n"
            f"**Captcha:** {E_CHECK + ' Увімкнена' if eco['captcha_enabled'] else E_CROSS + ' Вимкнена'}"
        )
    elif category == "bank":
        rate_str = f"{eco['bank_interest_rate']}%" if eco.get('bank_interest_rate', 0) > 0 else "вимк"
        intv_str = "щодня" if eco.get('bank_interest_interval') == 'daily' else "щотижня"
        embed.description = (
            f"{E_BANK} **Базовий ліміт:** `{eco['bank_base_limit']:,}` {curr}\n"
            f"{E_BOOST} **Множник за рівень:** `+{eco['bank_level_multiplier']:,}` {curr}\n"
            f"**Відсоток:** `{rate_str}` {intv_str}"
        )
    elif category == "rob":
        rob_str = f"{E_CHECK} Увімкнено" if eco["rob_enabled"] else f"{E_CROSS} Вимкнено"
        embed.description = (
            f"**Статус:** {rob_str}\n"
            f"{E_CLOCK} **КД:** `{fmt_duration(eco.get('rob_cooldown', 3600))}`\n"
            f"{E_RANDOM} **Шанс успіху:** `{eco['rob_chance']}%`\n"
            f"{E_INCOME} **Крадіжка від балансу:** `{eco.get('rob_percent_min', 10)}–{eco.get('rob_percent_max', 40)}%`\n"
            f"{E_WARN} **Штраф при провалі:** `{eco['rob_fine_percent']}%`\n"
            f"{E_SHIELD} **Мін. баланс жертви:** `{eco['rob_min_balance_percent']}%`\n"
            f"{E_CLOCK} **Час вистежування:** `{eco['rob_time']}с`"
        )
    elif category == "crime":
        crime_str = f"{E_CHECK} Увімкнено" if eco["crime_enabled"] else f"{E_CROSS} Вимкнено"
        embed.description = (
            f"**Статус:** {crime_str}\n"
            f"{E_CLOCK} **КД:** `{fmt_duration(eco['crime_cooldown'])}`\n"
            f"{E_WARN} **Бан-штраф:** `{fmt_duration(eco['crime_ban_duration'])}`\n\n"
            f"*При провалі крайму юзер не може використовувати eco-команди протягом бан-штрафу.*"
        )
    elif category == "gambling":
        gamb_str  = f"{E_CHECK} Увімкнено" if eco["gambling_enabled"] else f"{E_CROSS} Вимкнено"
        duel_timer  = eco.get("duel_timer", 15)
        duel_en   = f"{E_CHECK} Увімкнено" if eco.get("duel_enabled", True) else f"{E_CROSS} Вимк."
        draw_refund = eco.get("duel_draw_refund", True)
        draw_str    = f"{E_CHECK} Повертаються" if draw_refund else f"{E_CROSS} Згоряють"
        rtp_str     = f"{eco.get('casino_rtp', 95)}%"
        cap_str     = f"{eco.get('gambling_daily_cap', 0):,} {eco['currency_emoji']}" if eco.get('gambling_daily_cap', 0) > 0 else "вимк"
        embed.description = (
            f"🎰 **Казино:** {gamb_str}  •  **Макс. ставка:** `{eco['gambling_max_bet']:,}` {eco['currency_emoji']}\n"
            f"**RTP:** `{rtp_str}`  •  **Ліміт/день:** `{cap_str}`\n\n"
            f"⚔️ **Дуелі:** {duel_en}\n"
            f"{E_CLOCK} Таймер ходу: `{duel_timer}с`\n"
            f"⚔️ Ліміт раундів: `{duel_max}`\n"
            f"⚪ При нічиї ставки: {draw_str}\n\n"
            f"*Гемблінг вмикає /slots, /blackjack, /coinflip, /highlow, /roulette*"
        )
    elif category == "shop":
        curr = eco["currency_emoji"]
        prices = {
            "Щит": eco["shop_shield_price"],
            "Coin Буст": eco["shop_xp_boost_price"],
            "Лото": eco["shop_lottery_price"],
            "Crime Pass": eco["shop_crime_pass_price"],
        }
        lines = []
        for name, price in prices.items():
            status = f"`{price:,}` {curr}" if price > 0 else f"{E_CROSS} Вимкнено"
            lines.append(f"**{name}:** {status}")
        embed.description = "\n".join(lines)
    elif category == "transfers":
        tax = eco.get("transfer_tax_percent", 0)
        lim = eco.get("transfer_daily_limit", 0)
        curr = eco["currency_emoji"]
        tax_str = f"`{tax}%` (знімається при кожному переказі)" if tax > 0 else f"{E_CROSS} Вимкнено"
        lim_str = f"`{lim:,}` {curr} (скидається о 00:00)" if lim > 0 else f"{E_CROSS} Вимкнено"
        embed.description = (
            f"**Податок на переказ:** {tax_str}\n"
            f"**Ліміт переказів/день:** {lim_str}\n\n"
            f"*Ліміт — макс. сума яку гравець може **відправити** за 1 добу.*"
        )
    elif category == "quests":
        q_enabled = eco.get("quests_enabled", True)
        q_status  = f"{E_CHECK} Увімкнено" if q_enabled else f"{E_CROSS} Вимкнено"
        curr = eco["currency_emoji"]
        embed.description = (
            f"**Статус:** {q_status}\n"
            f"**Денних квестів:** `{eco.get('quests_daily_count', 3)}` шт — нагорода `{eco.get('quests_daily_reward', 200):,}` {curr}\n"
            f"**Тижневих квестів:** `{eco.get('quests_weekly_count', 2)}` шт — нагорода `{eco.get('quests_weekly_reward', 800):,}` {curr}"
        )
    elif category == "season":
        s_enabled = eco.get("season_enabled", False)
        s_status  = f"{E_CHECK} Увімкнено" if s_enabled else f"{E_CROSS} Вимкнено"
        s_dur    = eco.get("season_duration_days", 30)
        s_role   = eco.get("season_winner_role_id", 0)
        s_bonus  = eco.get("season_start_bonus", 0)
        s_start  = eco.get("season_start", 0)
        next_reset = s_start + s_dur * 86400 if s_start > 0 else None
        next_str  = f"<t:{next_reset}:R>" if next_reset else "не запущено"
        embed.description = (
            f"**Статус:** {s_status}\n"
            f"**Тривалість:** `{s_dur} днів`\n"
            f"**Роль переможців:** <@&{s_role}> (0 = вимк)\n"
            f"**Стартовий бонус:** `{s_bonus:,}` {eco['currency_emoji']}\n"
            f"**Наступне скидання:** {next_str}"
        )
    elif category == "games":
        enabled = eco.get("enabled_minigames", ["math", "higher_lower", "shell", "dice", "odd_emoji", "unscramble", "trivia", "typing", "guess", "reaction"])
        embed.description = (
            f"**Увімкнено міні-ігор:** `{len(enabled)}/10`\n\n"
            f"*Використовуйте меню нижче, щоб вибрати, які міні-ігри можуть випадати під час легкої роботи.*"
        )
    
    embed.set_footer(text="Оберіть категорію нижче для редагування")
    return embed

# ── Модальні форми ────────────────────────────────────────────────────────────

class GeneralModal(discord.ui.Modal, title="⚙️ Загальні налаштування"):
    currency_emoji = discord.ui.TextInput(label="Емодзі валюти", max_length=100)
    currency_name  = discord.ui.TextInput(label="Назва валюти", max_length=30)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.currency_emoji.default = eco["currency_emoji"]
        self.currency_name.default  = eco["currency_name"]

    async def on_submit(self, interaction: discord.Interaction):
        updates = {
            "economy.currency_emoji": self.currency_emoji.value.strip(),
            "economy.currency_name":  self.currency_name.value.strip(),
        }
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        embed = build_category_embed(self.main_view.eco, "general")
        cat_view = SetupCategoryView(self.main_view, "general")
        await interaction.response.edit_message(embed=embed, view=cat_view)

class PassiveModal(discord.ui.Modal, title="📈 Пасивний дохід"):
    msg_earn    = discord.ui.TextInput(label="Чат (мін-макс, напр. 5-10)", max_length=10)
    msg_cd      = discord.ui.TextInput(label="КД чату (секунди)", max_length=6)
    voice_earn  = discord.ui.TextInput(label="Войс (за хвилину)", max_length=5)
    react_earn  = discord.ui.TextInput(label="Реакції (за реакцію)", max_length=5)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        msg_earn = eco["msg_earn"]
        self.msg_earn.default   = f"{msg_earn[0]}-{msg_earn[1]}" if isinstance(msg_earn, list) else str(msg_earn)
        self.msg_cd.default     = str(eco["msg_cooldown"])
        self.voice_earn.default = str(eco["voice_earn"])
        self.react_earn.default = str(eco["reaction_earn"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            raw = self.msg_earn.value.strip()
            if "-" in raw:
                parts = [int(x.strip()) for x in raw.split("-")]
                msg_val = [min(parts), max(parts)]
            else:
                msg_val = int(raw)
            updates = {
                "economy.msg_earn":      msg_val,
                "economy.msg_cooldown":  int(self.msg_cd.value),
                "economy.voice_earn":    int(self.voice_earn.value),
                "economy.reaction_earn": int(self.react_earn.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Некоректні значення!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        embed = build_category_embed(self.main_view.eco, "passive")
        await interaction.response.edit_message(embed=embed, view=SetupCategoryView(self.main_view, "passive"))

class WorkAmountModal(discord.ui.Modal, title="💼 Work — Сума"):
    work_min = discord.ui.TextInput(label="Мінімум", max_length=10)
    work_max = discord.ui.TextInput(label="Максимум", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.work_min.default = str(eco["work_min"])
        self.work_max.default = str(eco["work_max"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.work_min": int(self.work_min.value),
                "economy.work_max": int(self.work_max.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "work"),
            view=SetupCategoryView(self.main_view, "work")
        )

class WorkCooldownModal(discord.ui.Modal, title="⏱ Work — Кулдаун"):
    cooldown = discord.ui.TextInput(label="КД (напр. 4h або 90m)", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.cooldown.default = fmt_duration_modal(eco["work_cooldown"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            seconds = parse_duration(self.cooldown.value)
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Формат: `4h`, `90m` або секунди числом.", ephemeral=True)
            return
        await save_eco(interaction.guild.id, {"economy.work_cooldown": seconds})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "work"),
            view=SetupCategoryView(self.main_view, "work")
        )

class WorkEventModal(discord.ui.Modal, title="🎲 Work — Налаштування події"):
    chance  = discord.ui.TextInput(label="Шанс події (%)", max_length=5)
    stake   = discord.ui.TextInput(label="Ставка події (% від заробленого)", max_length=5)
    timer   = discord.ui.TextInput(label="Час на хід у міні-грі (секунди)", max_length=4)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.chance.default = str(eco["event_chance"])
        self.stake.default  = str(eco["event_stake_percent"])
        self.timer.default  = str(eco["event_timer"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.event_chance":        int(self.chance.value),
                "economy.event_stake_percent": int(self.stake.value),
                "economy.event_timer":         int(self.timer.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "work"),
            view=SetupCategoryView(self.main_view, "work")
        )

class DailyAmountModal(discord.ui.Modal, title="📅 Daily — Сума"):
    amount  = discord.ui.TextInput(label="Базова сума", max_length=10)
    streak  = discord.ui.TextInput(label="Стрік-бонус за день", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.amount.default = str(eco["daily_amount"])
        self.streak.default = str(eco["daily_streak_bonus"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.daily_amount":       int(self.amount.value),
                "economy.daily_streak_bonus": int(self.streak.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "daily"),
            view=SetupCategoryView(self.main_view, "daily")
        )

class DailyCooldownModal(discord.ui.Modal, title="⏱ Daily — Кулдаун"):
    cooldown = discord.ui.TextInput(label="КД (напр. 24h або 1440m)", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.cooldown.default = fmt_duration_modal(eco["daily_cooldown"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            seconds = parse_duration(self.cooldown.value)
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Формат: `24h`, `1440m` або секунди.", ephemeral=True)
            return
        await save_eco(interaction.guild.id, {"economy.daily_cooldown": seconds})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "daily"),
            view=SetupCategoryView(self.main_view, "daily")
        )

class BankModal(discord.ui.Modal, title="🏦 Банк"):
    base_limit    = discord.ui.TextInput(label="Базовий ліміт", max_length=10)
    lvl_mult      = discord.ui.TextInput(label="Множник за рівень", max_length=10)
    interest_rate = discord.ui.TextInput(label="Відсоток % (напр. 1.5, 0=вимк)", max_length=5)
    interest_intv = discord.ui.TextInput(label="Період: daily або weekly", max_length=6)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.base_limit.default    = str(eco["bank_base_limit"])
        self.lvl_mult.default      = str(eco["bank_level_multiplier"])
        self.interest_rate.default = str(eco.get("bank_interest_rate", 0.0))
        self.interest_intv.default = eco.get("bank_interest_interval", "daily")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            interval = self.interest_intv.value.strip().lower()
            if interval not in ("daily", "weekly"):
                interval = "daily"
            updates = {
                "economy.bank_base_limit":        int(self.base_limit.value),
                "economy.bank_level_multiplier":  int(self.lvl_mult.value),
                "economy.bank_interest_rate":     float(self.interest_rate.value),
                "economy.bank_interest_interval": interval,
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "bank"),
            view=SetupCategoryView(self.main_view, "bank")
        )

class RobModal(discord.ui.Modal, title="🥷 Пограбування Основне"):
    chance    = discord.ui.TextInput(label="Шанс успіху (%)", max_length=5)
    fine      = discord.ui.TextInput(label="Штраф при провалі (%)", max_length=5)
    min_bal   = discord.ui.TextInput(label="Мін. баланс жертви (%)", max_length=5)
    rob_time  = discord.ui.TextInput(label="Час вистежування (напр. 30s, 2m)", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.chance.default   = str(eco.get("rob_chance", 40))
        self.fine.default     = str(eco.get("rob_fine_percent", 25))
        self.min_bal.default  = str(eco.get("rob_min_balance_percent", 20))
        self.rob_time.default = fmt_duration_modal(eco.get("rob_time", 10))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.rob_chance":              int(self.chance.value),
                "economy.rob_fine_percent":        int(self.fine.value),
                "economy.rob_min_balance_percent": int(self.min_bal.value),
                "economy.rob_time":                parse_duration(self.rob_time.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "rob"),
            view=SetupCategoryView(self.main_view, "rob")
        )

class RobAdvancedModal(discord.ui.Modal, title="🥷 Пограбування Додатково"):
    pct_min   = discord.ui.TextInput(label="Мін. % вкраденого", max_length=5)
    pct_max   = discord.ui.TextInput(label="Макс. % вкраденого", max_length=5)
    cooldown  = discord.ui.TextInput(label="Кулдаун (напр. 1h)", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.pct_min.default  = str(eco.get("rob_percent_min", 10))
        self.pct_max.default  = str(eco.get("rob_percent_max", 40))
        self.cooldown.default = fmt_duration_modal(eco.get("rob_cooldown", 3600))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.rob_percent_min": int(self.pct_min.value),
                "economy.rob_percent_max": int(self.pct_max.value),
                "economy.rob_cooldown":    parse_duration(self.cooldown.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "rob"),
            view=SetupCategoryView(self.main_view, "rob")
        )

class CrimeModal(discord.ui.Modal, title="🦹 Крайм"):
    cooldown     = discord.ui.TextInput(label="КД (напр. 8h)", max_length=10)
    ban_duration = discord.ui.TextInput(label="Бан при провалі (напр. 30m)", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.cooldown.default     = fmt_duration_modal(eco["crime_cooldown"])
        self.ban_duration.default = fmt_duration_modal(eco["crime_ban_duration"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.crime_cooldown":     parse_duration(self.cooldown.value),
                "economy.crime_ban_duration": parse_duration(self.ban_duration.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Формат: `8h`, `30m`.", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "crime"),
            view=SetupCategoryView(self.main_view, "crime")
        )

class GamblingModal(discord.ui.Modal, title="🎰 Гемблінг"):
    max_bet    = discord.ui.TextInput(label="Максимальна ставка", max_length=10)
    duel_timer = discord.ui.TextInput(label="Таймер дуелі (секунди)", max_length=4)
    max_rounds = discord.ui.TextInput(label="Ліміт раундів дуелі", max_length=3)
    casino_rtp = discord.ui.TextInput(label="Casino RTP % (0-100, 95=стандарт)", max_length=3)
    daily_cap  = discord.ui.TextInput(label="Ліміт виграшу/день (0=вимк)", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.max_bet.default    = str(eco["gambling_max_bet"])
        self.duel_timer.default = str(eco.get("duel_timer", 15))
        self.max_rounds.default = str(eco.get("duel_max_rounds", 9))
        self.casino_rtp.default = str(eco.get("casino_rtp", 95))
        self.daily_cap.default  = str(eco.get("gambling_daily_cap", 0))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.gambling_max_bet":   int(self.max_bet.value),
                "economy.duel_timer":         int(self.duel_timer.value),
                "economy.duel_max_rounds":    int(self.max_rounds.value),
                "economy.casino_rtp":         max(0, min(100, int(self.casino_rtp.value))),
                "economy.gambling_daily_cap": int(self.daily_cap.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "gambling"),
            view=SetupCategoryView(self.main_view, "gambling")
        )

class ShopPricesModal(discord.ui.Modal, title="🏪 Ціни магазину"):
    shield     = discord.ui.TextInput(label="Щит (0 = вимк)", max_length=10)
    xp_boost   = discord.ui.TextInput(label="XP Буст (0 = вимк)", max_length=10)
    lottery    = discord.ui.TextInput(label="Лото квиток (0 = вимк)", max_length=10)
    crime_pass = discord.ui.TextInput(label="Crime Pass (0 = вимк)", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.shield.default     = str(eco["shop_shield_price"])
        self.xp_boost.default   = str(eco["shop_xp_boost_price"])
        self.lottery.default    = str(eco["shop_lottery_price"])
        self.crime_pass.default = str(eco["shop_crime_pass_price"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.shop_shield_price":     int(self.shield.value),
                "economy.shop_xp_boost_price":   int(self.xp_boost.value),
                "economy.shop_lottery_price":     int(self.lottery.value),
                "economy.shop_crime_pass_price":  int(self.crime_pass.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "shop"),
            view=SetupCategoryView(self.main_view, "shop")
        )

# ── Select Меню категорій ─────────────────────────────────────────────────────

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Загальне",        value="general",  description="Валюта, сезон та перекази",              emoji=discord.PartialEmoji.from_str(E_SETTING)),
            discord.SelectOption(label="Пасивний дохід",  value="passive",  description="Чат, войс, реакції",                   emoji=discord.PartialEmoji.from_str(E_INCOME)),
            discord.SelectOption(label="Робота",          value="work",     description="Сума, КД, режим, події",               emoji=discord.PartialEmoji.from_str(E_WORK)),
            discord.SelectOption(label="Daily",           value="daily",    description="Нагорода, стрік, captcha",             emoji=discord.PartialEmoji.from_str(E_DAILY)),
            discord.SelectOption(label="Банк",            value="bank",     description="Ліміти та множники",                   emoji=discord.PartialEmoji.from_str(E_BANK)),
            discord.SelectOption(label="Пограбування",   value="rob",      description="Шанс, штраф, мін. баланс",             emoji=discord.PartialEmoji.from_str(E_ROB)),
            discord.SelectOption(label="Крайм",          value="crime",    description="КД та штраф-бан",                     emoji=discord.PartialEmoji.from_str(E_CRIME)),
            discord.SelectOption(label="Ігри та Казино", value="gambling",  description="Казино, Дуелі та Міні-ігри роботи",     emoji=discord.PartialEmoji.from_str(E_STATS)),
            discord.SelectOption(label="Магазин",        value="shop",      description="Ціни системних предметів",             emoji=discord.PartialEmoji.from_str(E_SHOP)),
            discord.SelectOption(label="Квести",         value="quests",   description="Налаштування денних/тижневих завдань", emoji=discord.PartialEmoji.from_str("<:reasonqiestion:1476209697919860777>")),
        ]
        super().__init__(placeholder="Оберіть категорію...", options=options)

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        main_view = self.view
        embed = build_category_embed(main_view.eco, cat)
        cat_view = SetupCategoryView(main_view, cat)
        await interaction.response.edit_message(embed=embed, view=cat_view)

class EcoSetupView(discord.ui.View):
    def __init__(self, eco: dict):
        super().__init__(timeout=900)
        self.eco = eco
        self.add_item(CategorySelect())

class MinigamesSelect(discord.ui.Select):
    def __init__(self, eco: dict, main_view: EcoSetupView):
        self.main_view = main_view
        enabled = eco.get("enabled_minigames", ["math", "higher_lower", "shell", "dice", "odd_emoji", "unscramble", "trivia", "typing", "guess", "reaction"])
        options = [
            discord.SelectOption(label="Математика", value="math", default="math" in enabled),
            discord.SelectOption(label="Більше Менше", value="higher_lower", default="higher_lower" in enabled),
            discord.SelectOption(label="Наперстки", value="shell", default="shell" in enabled),
            discord.SelectOption(label="Кості", value="dice", default="dice" in enabled),
            discord.SelectOption(label="Зайвий Емодзі", value="odd_emoji", default="odd_emoji" in enabled),
            discord.SelectOption(label="Анаграма", value="unscramble", default="unscramble" in enabled),
            discord.SelectOption(label="Вікторина", value="trivia", default="trivia" in enabled),
            discord.SelectOption(label="Швидкий друк", value="typing", default="typing" in enabled),
            discord.SelectOption(label="Відгадай число", value="guess", default="guess" in enabled),
            discord.SelectOption(label="Реакція", value="reaction", default="reaction" in enabled),
        ]
        super().__init__(placeholder="Увімкнені міні-ігри...", min_values=1, max_values=10, options=options)

    async def callback(self, interaction: discord.Interaction):
        await save_eco(interaction.guild.id, {"economy.enabled_minigames": self.values})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "games"),
            view=SetupCategoryView(self.main_view, "games")
        )

# ── Підменю категорії ─────────────────────────────────────────────────────────

class SetupCategoryView(discord.ui.View):
    def __init__(self, main_view: EcoSetupView, category: str):
        super().__init__(timeout=900)
        self.main_view = main_view
        self.category  = category
        eco = main_view.eco

        # ── Кнопки специфічні для категорії ──────────────────────────────────
        if category == "general":
            self._toggle("economy.enabled", eco["enabled"], "Економіка", self._toggle_cb)
            
            s_enabled = eco.get("season_enabled", False)
            s_style   = discord.ButtonStyle.success if s_enabled else discord.ButtonStyle.secondary
            s_label   = "Сезон: ВКЛ" if s_enabled else "Сезон: ВИКЛ"
            sb = discord.ui.Button(label=s_label, style=s_style)
            sb.callback = lambda i: self._toggle_bool(i, "economy.season_enabled", not s_enabled, "general")
            self.add_item(sb)

            self._add("Валюта", discord.ButtonStyle.secondary, self._general_cb)
            self._add("Перекази", discord.ButtonStyle.secondary, self._transfer_cb)
            self._add("Сезон", discord.ButtonStyle.secondary, self._season_cb)
            
            reset_btn = discord.ui.Button(label="Скинути зараз", style=discord.ButtonStyle.secondary, row=1)
            reset_btn.callback = self._season_reset_now
            self.add_item(reset_btn)

        elif category == "passive":
            self._add("Змінити налаштування", discord.ButtonStyle.secondary, self._passive_cb)

        elif category == "work":
            self._add("Сума заробітку",       discord.ButtonStyle.secondary, self._work_amount_cb)
            self._add("Кулдаун",              discord.ButtonStyle.secondary, self._work_cd_cb)
            self._add("Налаштування події",   discord.ButtonStyle.secondary, self._work_event_cb)
            
            mode = eco.get("work_type", "both")
            styles = {
                "simple":  discord.ButtonStyle.success if mode == "simple"  else discord.ButtonStyle.secondary,
                "complex": discord.ButtonStyle.danger  if mode == "complex" else discord.ButtonStyle.secondary,
                "both":    discord.ButtonStyle.primary if mode == "both"    else discord.ButtonStyle.secondary,
            }
            b1 = discord.ui.Button(label="Лише Легка",   style=styles["simple"],  row=1)
            b2 = discord.ui.Button(label="Лише Складна", style=styles["complex"], row=1)
            b3 = discord.ui.Button(label="Обидва",       style=styles["both"],    row=1)
            b1.callback = lambda i: self._set_work_mode(i, "simple")
            b2.callback = lambda i: self._set_work_mode(i, "complex")
            b3.callback = lambda i: self._set_work_mode(i, "both")
            self.add_item(b1)
            self.add_item(b2)
            self.add_item(b3)
            self._add("Етапи складної", discord.ButtonStyle.secondary, self._work_stages_cb, emoji_str=E_SETTING)

        elif category == "daily":
            self._add("Нагорода та стрік", discord.ButtonStyle.secondary, self._daily_amount_cb)
            self._add("Кулдаун",            discord.ButtonStyle.secondary, self._daily_cd_cb)
            cap_style = discord.ButtonStyle.success if eco["captcha_enabled"] else discord.ButtonStyle.secondary
            cap_label = "Captcha: ВКЛ" if eco["captcha_enabled"] else "Captcha: ВИКЛ"
            b = discord.ui.Button(label=cap_label, style=cap_style, row=1)
            b.callback = self._toggle_captcha
            self.add_item(b)

        elif category == "bank":
            self._add("Змінити ліміти", discord.ButtonStyle.secondary, self._bank_cb)

        elif category == "rob":
            rob_style = discord.ButtonStyle.success if eco["rob_enabled"] else discord.ButtonStyle.secondary
            rob_label = "Пограбування: ВКЛ" if eco["rob_enabled"] else "Пограбування: ВИКЛ"
            b = discord.ui.Button(label=rob_label, style=rob_style)
            b.callback = lambda i: self._toggle_bool(i, "economy.rob_enabled", not eco["rob_enabled"], "rob")
            self.add_item(b)
            self._add("Основне", discord.ButtonStyle.secondary, self._rob_cb)
            self._add("Відсоток та Кулдаун", discord.ButtonStyle.secondary, self._rob_adv_cb)

        elif category == "crime":
            crime_style = discord.ButtonStyle.success if eco["crime_enabled"] else discord.ButtonStyle.secondary
            crime_label = "Крайм: ВКЛ" if eco["crime_enabled"] else "Крайм: ВИКЛ"
            b = discord.ui.Button(label=crime_label, style=crime_style)
            b.callback = lambda i: self._toggle_bool(i, "economy.crime_enabled", not eco["crime_enabled"], "crime")
            self.add_item(b)
            self._add("Налаштування КД", discord.ButtonStyle.secondary, self._crime_cb)

        elif category == "gambling":
            gamb_style = discord.ButtonStyle.success if eco["gambling_enabled"] else discord.ButtonStyle.secondary
            gamb_label = "Казино & Ігри: ВКЛ" if eco["gambling_enabled"] else "Казино & Ігри: ВИКЛ"
            b = discord.ui.Button(label=gamb_label, style=gamb_style)
            b.callback = lambda i: self._toggle_bool(i, "economy.gambling_enabled", not eco["gambling_enabled"], "gambling")
            self.add_item(b)
            
            self._add("Налаштування", discord.ButtonStyle.secondary, self._gambling_cb)
            
            draw_refund   = eco.get("duel_draw_refund", True)
            draw_style    = discord.ButtonStyle.success if draw_refund else discord.ButtonStyle.secondary
            draw_label    = "Нічия: повертаються" if draw_refund else "Нічия: згорають"
            draw_btn      = discord.ui.Button(label=draw_label, style=draw_style)
            draw_btn.callback = lambda i: self._toggle_bool(i, "economy.duel_draw_refund", not draw_refund, "gambling")
            self.add_item(draw_btn)
            
            duel_en       = eco.get("duel_enabled", True)
            duel_style    = discord.ButtonStyle.success if duel_en else discord.ButtonStyle.secondary
            duel_label    = "Дуелі: ВКЛ" if duel_en else "Дуелі: ВИКЛ"
            duel_btn      = discord.ui.Button(label=duel_label, style=duel_style)
            duel_btn.callback = lambda i: self._toggle_bool(i, "economy.duel_enabled", not duel_en, "gambling")
            self.add_item(duel_btn)

            self.add_item(MinigamesSelect(eco, self.main_view))

        elif category == "shop":
            self._add("Ціни предметів", discord.ButtonStyle.secondary, self._shop_cb)
            
            roles_btn = discord.ui.Button(label="Керування кастом-ролями", style=discord.ButtonStyle.primary, emoji="🎭")
            roles_btn.callback = self._shop_roles_cb
            self.add_item(roles_btn)

        elif category == "quests":
            q_enabled = eco.get("quests_enabled", True)
            q_style   = discord.ButtonStyle.success if q_enabled else discord.ButtonStyle.secondary
            q_label   = "Квести: ВКЛ" if q_enabled else "Квести: ВИКЛ"
            qb = discord.ui.Button(label=q_label, style=q_style)
            qb.callback = lambda i: self._toggle_bool(i, "economy.quests_enabled", not q_enabled, "quests")
            self.add_item(qb)
            self._add("Налаштування", discord.ButtonStyle.secondary, self._quests_cb)

        back = discord.ui.Button(
            emoji=discord.PartialEmoji.from_str(E_LEFT),
            style=discord.ButtonStyle.secondary,
            row=4
        )
        back.callback = self._back_cb
        self.add_item(back)

    def _add(self, label: str, style: discord.ButtonStyle, callback, emoji_str: str = None):
        kwargs = {"label": label, "style": style}
        if emoji_str:
            kwargs["emoji"] = discord.PartialEmoji.from_str(emoji_str)
        btn = discord.ui.Button(**kwargs)
        btn.callback = callback
        self.add_item(btn)

    def _toggle(self, key: str, current: bool, label: str, callback):
        style = discord.ButtonStyle.success if current else discord.ButtonStyle.secondary
        text  = f"{label}: ВКЛ" if current else f"{label}: ВИКЛ"
        emoji = discord.PartialEmoji.from_str(E_CHECK if current else E_CROSS)
        btn   = discord.ui.Button(label=text, style=style, emoji=emoji)
        btn.callback = callback
        self.add_item(btn)

    async def _back_cb(self, interaction: discord.Interaction):
        view = EcoSetupView(self.main_view.eco)
        await interaction.response.edit_message(embed=build_main_embed(self.main_view.eco), view=view)

    async def _toggle_cb(self, interaction: discord.Interaction):
        new_val = not self.main_view.eco["enabled"]
        await self._toggle_bool(interaction, "economy.enabled", new_val, "general")

    async def _toggle_bool(self, interaction: discord.Interaction, key: str, new_val: bool, cat: str):
        await save_eco(interaction.guild.id, {key: new_val})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, cat),
            view=SetupCategoryView(self.main_view, cat)
        )

    async def _toggle_captcha(self, interaction: discord.Interaction):
        new_val = not self.main_view.eco["captcha_enabled"]
        await self._toggle_bool(interaction, "economy.captcha_enabled", new_val, "daily")

    async def _set_work_mode(self, interaction: discord.Interaction, mode: str):
        await save_eco(interaction.guild.id, {"economy.work_type": mode})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "work"),
            view=SetupCategoryView(self.main_view, "work")
        )

    async def _general_cb(self, i):   await i.response.send_modal(GeneralModal(self.main_view, self.main_view.eco))
    async def _passive_cb(self, i):   await i.response.send_modal(PassiveModal(self.main_view, self.main_view.eco))
    async def _work_amount_cb(self, i): await i.response.send_modal(WorkAmountModal(self.main_view, self.main_view.eco))
    async def _work_cd_cb(self, i):   await i.response.send_modal(WorkCooldownModal(self.main_view, self.main_view.eco))
    async def _work_event_cb(self, i): await i.response.send_modal(WorkEventModal(self.main_view, self.main_view.eco))
    async def _work_stages_cb(self, i):
        class WorkStagesModal(discord.ui.Modal, title="💼 Work — Етапи складної"):
            stages = discord.ui.TextInput(label="Кількість етапів (1-5)", max_length=2)
            def __init__(self, mv, eco_v):
                super().__init__()
                self.mv = mv
                self.stages.default = str(eco_v.get("work_complex_stages", 3))
            async def on_submit(self, interaction: discord.Interaction):
                try:
                    val = max(1, min(5, int(self.stages.value)))
                    await save_eco(interaction.guild.id, {"economy.work_complex_stages": val})
                except ValueError:
                    return await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
                ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
                self.mv.eco = get_eco(ctx)
                await interaction.response.edit_message(
                    embed=build_category_embed(self.mv.eco, "work"),
                    view=SetupCategoryView(self.mv, "work")
                )
        await i.response.send_modal(WorkStagesModal(self.main_view, self.main_view.eco))

    async def _daily_amount_cb(self, i): await i.response.send_modal(DailyAmountModal(self.main_view, self.main_view.eco))
    async def _daily_cd_cb(self, i):  await i.response.send_modal(DailyCooldownModal(self.main_view, self.main_view.eco))
    async def _bank_cb(self, i):      await i.response.send_modal(BankModal(self.main_view, self.main_view.eco))
    async def _rob_cb(self, i):       await i.response.send_modal(RobModal(self.main_view, self.main_view.eco))
    async def _rob_adv_cb(self, i):   await i.response.send_modal(RobAdvancedModal(self.main_view, self.main_view.eco))
    async def _crime_cb(self, i):     await i.response.send_modal(CrimeModal(self.main_view, self.main_view.eco))
    async def _gambling_cb(self, i):  await i.response.send_modal(GamblingModal(self.main_view, self.main_view.eco))
    async def _shop_cb(self, i):      await i.response.send_modal(ShopPricesModal(self.main_view, self.main_view.eco))
    
    async def _shop_roles_cb(self, interaction: discord.Interaction):
        
        await interaction.response.edit_message(
            embed=build_shop_roles_embed(self.main_view.eco, interaction.guild),
            view=ShopRolesView(self.main_view, interaction.guild)
        )
        
    async def _games_cb(self, i):     await i.response.send_modal(GamesModal(self.main_view, self.main_view.eco))
    async def _transfer_cb(self, i):  await i.response.send_modal(TransferModal(self.main_view, self.main_view.eco))
    async def _quests_cb(self, i):    await i.response.send_modal(QuestsModal(self.main_view, self.main_view.eco))
    async def _season_cb(self, i):    await i.response.send_modal(SeasonModal(self.main_view, self.main_view.eco))

    async def _season_reset_now(self, interaction: discord.Interaction):
        """Миттєво скидає сезон та публікує підсумок у канал."""
        from services.scheduler import perform_season_reset
        await interaction.response.defer(ephemeral=True)
        try:
            await perform_season_reset(interaction.guild)
            ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
            self.main_view.eco = get_eco(ctx)
            await interaction.followup.send(
                f"{E_CHECK} Сезон скинуто! Підсумки опубліковані в канал, нові балланси встановлено.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"{E_CROSS} Помилка: `{e}`", ephemeral=True)

class TransferModal(discord.ui.Modal, title="↔️ Перекази"):
    tax     = discord.ui.TextInput(label="Податок на переказ % (0=вимк)", max_length=3)
    day_lim = discord.ui.TextInput(label="Ліміт суми/день (0=вимк)", max_length=12)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.tax.default     = str(eco.get("transfer_tax_percent", 0))
        self.day_lim.default = str(eco.get("transfer_daily_limit", 0))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.transfer_tax_percent": max(0, min(50, int(self.tax.value))),
                "economy.transfer_daily_limit": int(self.day_lim.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "transfers"),
            view=SetupCategoryView(self.main_view, "transfers")
        )

class QuestsModal(discord.ui.Modal, title="📋 Квести"):
    daily_reward  = discord.ui.TextInput(label="Початкова нагор. за денний квест", max_length=8)
    weekly_reward = discord.ui.TextInput(label="Початкова нагор. за тижневий квест", max_length=8)
    multiplier    = discord.ui.TextInput(label="Множник (донат за 1 одн. цілі)", max_length=5)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.daily_reward.default  = str(eco.get("quests_daily_reward", 200))
        self.weekly_reward.default = str(eco.get("quests_weekly_reward", 800))
        self.multiplier.default    = str(eco.get("quests_target_multiplier", 50))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.quests_daily_reward":  int(self.daily_reward.value),
                "economy.quests_weekly_reward": int(self.weekly_reward.value),
                "economy.quests_target_multiplier": int(self.multiplier.value),
            }
        except ValueError:
            await interaction.response.send_message(f"Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "quests"),
            view=SetupCategoryView(self.main_view, "quests")
        )

class SeasonModal(discord.ui.Modal, title="🏆 Сезон"):
    duration    = discord.ui.TextInput(label="Тривалість (днів)", max_length=4)
    role_id     = discord.ui.TextInput(label="ID ролі переможців (0=без ролі)", max_length=20)
    start_bonus = discord.ui.TextInput(label="Стартовий бонус монет", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.duration.default    = str(eco.get("season_duration_days", 30))
        self.role_id.default     = str(eco.get("season_winner_role_id", 0))
        self.start_bonus.default = str(eco.get("season_start_bonus", 0))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.season_duration_days":  max(1, int(self.duration.value)),
                "economy.season_winner_role_id": int(self.role_id.value),
                "economy.season_start_bonus":    int(self.start_bonus.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "season"),
            view=SetupCategoryView(self.main_view, "season")
        )

# ── Керування Ролями Магазину ────────────────────────────────────────────────

def build_shop_roles_embed(eco: dict, guild: discord.Guild) -> discord.Embed:
    curr = eco.get("currency_emoji", E_COIN)
    shop_roles = eco.get("shop_roles", [])
    
    embed = discord.Embed(
        title="🎭 Магазин: Кастомні ролі",
        description="Тут ви можете додати ролі для продажу або видалити існуючі.\n\n**Поточні ролі в продажу:**",
        color=EMBED_COLOR
    )
    
    if not shop_roles:
        embed.description += "\n\n*Немає жодної ролі на продаж.*"
    else:
        lines = []
        for r in shop_roles:
            role_obj = guild.get_role(r["role_id"])
            role_name = role_obj.mention if role_obj else f"Unknown Role ({r['role_id']})"
            lines.append(f"• {role_name} — **{r['price']:,}** {curr}")
        embed.description += "\n\n" + "\n".join(lines)
        
    embed.set_footer(text="Використовуйте меню для додавання/видалення")
    return embed

class ShopAddRoleModal(discord.ui.Modal, title="Додати Роль в Магазин"):
    price = discord.ui.TextInput(label="Ціна ролі", max_length=10)

    def __init__(self, main_view, role_id: int, guild: discord.Guild):
        super().__init__()
        self.main_view = main_view
        self.role_id = role_id
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_val = int(self.price.value)
            if price_val <= 0: raise ValueError
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Некоректна ціна!", ephemeral=True)
            return

        shop_roles = self.main_view.eco.get("shop_roles", [])
        
        role_exists = False
        for r in shop_roles:
            if r["role_id"] == self.role_id:
                r["price"] = price_val
                role_exists = True
                break
                
        if not role_exists:
            shop_roles.append({"role_id": self.role_id, "price": price_val})

        await save_eco(interaction.guild.id, {"economy.shop_roles": shop_roles})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        
        await interaction.response.edit_message(
            embed=build_shop_roles_embed(self.main_view.eco, self.guild),
            view=ShopRolesView(self.main_view, self.guild)
        )

class ShopAddRoleSelect(discord.ui.RoleSelect):
    def __init__(self, main_view, guild: discord.Guild):
        super().__init__(placeholder="Виберіть роль для додавання/редагування...")
        self.main_view = main_view
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        role_id = self.values[0].id
        await interaction.response.send_modal(ShopAddRoleModal(self.main_view, role_id, self.guild))

class ShopRemoveRoleSelect(discord.ui.Select):
    def __init__(self, main_view, guild: discord.Guild, shop_roles: list):
        self.main_view = main_view
        self.guild = guild
        
        options = []
        for r in shop_roles:
            r_obj = guild.get_role(r["role_id"])
            name_str = r_obj.name if r_obj else f"ID: {r['role_id']}"
            options.append(discord.SelectOption(
                label=f"Видалити {name_str}",
                value=str(r["role_id"]),
                description=f"Ціна: {r['price']}"
            ))
            
        super().__init__(placeholder="Виберіть роль для видалення з продажу...", options=options)

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        shop_roles = self.main_view.eco.get("shop_roles", [])
        new_shop_roles = [r for r in shop_roles if r["role_id"] != role_id]
        
        await save_eco(interaction.guild.id, {"economy.shop_roles": new_shop_roles})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        
        await interaction.response.edit_message(
            embed=build_shop_roles_embed(self.main_view.eco, self.guild),
            view=ShopRolesView(self.main_view, self.guild)
        )

class ShopRolesView(discord.ui.View):
    def __init__(self, main_view, guild: discord.Guild):
        super().__init__(timeout=900)
        self.main_view = main_view
        self.guild = guild
        
        self.add_item(ShopAddRoleSelect(main_view, guild))
        
        shop_roles = main_view.eco.get("shop_roles", [])
        if shop_roles:
            
            self.add_item(ShopRemoveRoleSelect(main_view, guild, shop_roles[:25]))
            
        back_btn = discord.ui.Button(label="Назад до налаштувань Магазину", style=discord.ButtonStyle.secondary, emoji=E_LEFT, row=3)
        back_btn.callback = self._back_cb
        self.add_item(back_btn)

    async def _back_cb(self, interaction: discord.Interaction):
        
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "shop"),
            view=SetupCategoryView(self.main_view, "shop")
        )

# ── Cog ───────────────────────────────────────────────────────────────────────

class EconomySetup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="economy_setup", description="[Admin] Налаштувати серверну економіку")
    @app_commands.default_permissions(administrator=True)
    async def economy_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        eco = get_eco(settings)
        embed = build_main_embed(eco)
        view  = EcoSetupView(eco)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(EconomySetup(bot))

