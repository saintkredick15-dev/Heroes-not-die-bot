import discord
from config.constants import Emojis as _E
from modules.db import get_database
from utils.ui_contract import add_section, compact_kv, set_surface_footer, surface_embed

db = get_database()

E_CHECK = _E.CHECK.value
E_CROSS = _E.CROSS.value
E_WARN = _E.WARN.value
E_CLOCK = _E.CLOCK.value
E_SETTING = _E.SETTINGS.value
E_CHAT = _E.CHAT.value
E_MICRO = _E.MICRO.value
E_STAR = _E.STAR.value
E_WORK = _E.WORK.value
E_WORKS = _E.WORKS.value
E_DAILY = _E.DAY31.value
E_BANK = _E.BANK.value
E_ROB = _E.ROBBERY.value
E_INCOME = _E.COINS.value
E_RANDOM = _E.CELEBRATION.value
E_SHIELD = _E.SHIELD.value
E_FLAME = _E.FLAME.value
E_BOOST = _E.BOOST.value
E_HISTORY = _E.HISTORY.value
E_LEFT = _E.LEFT.value
E_STATS = _E.STATS.value
E_CRIME = _E.CRIMEPASS.value
E_SHOP = _E.SHOP.value
E_GAME = _E.STATS.value
E_AUCTION = _E.AUCTION.value
E_HELP = _E.HELP.value
E_WALLET = _E.WALLET.value
E_SLOTS = _E.SLOTS_ALT.value
E_SWORDS = _E.SWORDS.value
E_MINUS = _E.MINUS.value
E_PLUS = _E.PLUS.value
E_TRANSFER = _E.TRANSFER.value
E_CLIPBOARD = _E.CLIPBOARD.value
E_ROLE = _E.ROLE.value
E_TROPHY = _E.TROPHY.value
E_MEDAL = _E.MEDAL.value
E_TRASH = _E.TRASH.value

EMBED_COLOR = 0x1A1A2E
CANONICAL_COIN = _E.COIN.value
LEGACY_CURRENCY_EMOJIS = {"💰", "🪙", "$", "Coin", "coin", ":coin:", "<:coin:1485610808003133552>", "<:coin_emoji:1485610808003133552>"}

DEFAULT_ECO = {
    "enabled": True,
    "currency_emoji": CANONICAL_COIN,
    "currency_name": "Coin",
    "msg_earn": [5, 10],
    "msg_cooldown": 60,
    "voice_earn": 3,
    "reaction_earn": 2,
    "work_min": 50,
    "work_max": 400,
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
    "crime_bribe_percent": 75,
    "crime_bribe_timeout": 15,
    "gambling_enabled": False,
    "gambling_max_bet": 10000,
    "gambling_daily_cap": 0,
    "gambling_cooldown": 0,
    "duel_timer": 15,
    "duel_max_rounds": 9,
    "duel_draw_refund": True,
    "casino_rtp": 90,
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
    "shop_lootbox_common_price": 2500,
    "shop_lootbox_rare_price": 10000,
    "shop_crime_pass_price": 3000,
    "account_age_min_days": 14,
    "inflation_enabled": True,
    "inflation_max_limit": 3.0,
    "inflation_multiplier": 1.0,
    "lb_com_jackpot_pct": 10,
    "lb_rare_jackpot_pct": 5,
    "lb_rare_pass_pct": 10,
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
    "season_winner_roles": {},
    "season_announce_channel_id": 0,
    "season_start_bonus": 0,
    "season_start": 0,
    "season_number": 1,
    "season_history": [],
    "auction_channel_id": 0,
    "auction_anti_snipe_seconds": 30,
    "auction_min_increment": 100,
    "auction_step_presets": [100, 1000, 5000],
    "fund_enabled": False,
    "fund_goal": 1000000,
    "fund_current": 0,
    "duel_enabled": True,
    "work_complex_stages": 3,
    "enabled_minigames": ["math", "higher_lower", "shell", "dice", "odd_emoji", "unscramble", "trivia", "typing", "guess", "reaction"],
}


def parse_duration(value: str) -> int:
    import re

    v = value.strip().lower()
    v = re.sub(r"(хв|хвил?)", "m", v)
    v = re.sub(r"г", "h", v)
    v = re.sub(r"с(?!\d)", "s", v)

    pattern = re.compile(r"^(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?$")
    match = pattern.fullmatch(v)
    if match and any(match.group(g) for g in ("h", "m", "s")):
        h = int(match.group("h") or 0)
        m = int(match.group("m") or 0)
        s = int(match.group("s") or 0)
        total = h * 3600 + m * 60 + s
        if total <= 0:
            raise ValueError("Duration must be > 0")
        return total

    return int(float(v))


def fmt_duration_modal(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    s = rem % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s:
        parts.append(f"{s}s")
    return "".join(parts) or "0s"


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h and m:
        return f"{h}г {m}хв"
    if h:
        return f"{h}г"
    return f"{m}хв"


def normalize_currency_emoji(value) -> str:
    # Full servers use one canonical coin. Any legacy/custom variant is collapsed to it.
    if not isinstance(value, str):
        return CANONICAL_COIN
    normalized = value.strip()
    if not normalized:
        return CANONICAL_COIN
    if normalized == CANONICAL_COIN:
        return CANONICAL_COIN
    if normalized in LEGACY_CURRENCY_EMOJIS or "1485610808003133552" in normalized:
        return CANONICAL_COIN
    return CANONICAL_COIN


def get_eco(settings: dict) -> dict:
    eco = {**DEFAULT_ECO, **settings.get("economy", {})}
    eco["currency_emoji"] = normalize_currency_emoji(eco.get("currency_emoji"))
    return eco


async def save_eco(guild_id: int, updates: dict):
    from modules.db import invalidate_guild_settings

    normalized_updates = dict(updates)
    for key, value in list(normalized_updates.items()):
        if key.endswith("currency_emoji"):
            normalized_updates[key] = normalize_currency_emoji(value)
        elif key == "economy" and isinstance(value, dict):
            normalized_economy = dict(value)
            normalized_economy["currency_emoji"] = normalize_currency_emoji(normalized_economy.get("currency_emoji"))
            normalized_updates[key] = normalized_economy

    await db.guild_settings.update_one({"_id": guild_id}, {"$set": normalized_updates}, upsert=True)
    await invalidate_guild_settings(guild_id)


def _status_text(enabled: bool) -> str:
    return f"{E_CHECK} Увімкнено" if enabled else f"{E_CROSS} Вимкнено"


def _range_text(value) -> str:
    if isinstance(value, list) and len(value) == 2:
        return f"{value[0]}-{value[1]}"
    return str(value)


def build_main_embed(eco: dict) -> discord.Embed:
    curr = normalize_currency_emoji(eco.get("currency_emoji"))
    work_modes = {"simple": "Легка", "complex": "Складна", "both": "Обидва режими"}
    msg_str = _range_text(eco["msg_earn"])
    interest_rate = eco.get("bank_interest_rate", 0)
    interest_text = (
        f"`{interest_rate}%` / {'день' if eco.get('bank_interest_interval') == 'daily' else 'тиждень'}"
        if interest_rate > 0
        else f"{E_CROSS} Вимкнено"
    )
    minigames_enabled = len(eco.get("enabled_minigames", []))
    shop_roles = len(eco.get("shop_roles", []))
    auction_channel = f"<#{eco['auction_channel_id']}>" if eco.get("auction_channel_id") else f"{E_CROSS} Не вибрано"

    embed = surface_embed(
        "admin",
        f"{E_SETTING} Налаштування економіки",
        "Огляд ключових систем і базових параметрів економіки сервера.",
    )
    add_section(
        embed,
        f"{E_SETTING} Ядро",
        [
            compact_kv("Економіка", _status_text(eco["enabled"])),
            compact_kv("Валюта", f"{curr} `{eco['currency_name']}`"),
            compact_kv("Сезон", _status_text(eco.get("season_enabled", False))),
            compact_kv("Перекази", f"податок `{eco.get('transfer_tax_percent', 0)}%` • ліміт `{eco.get('transfer_daily_limit', 0):,}` {curr}"),
        ],
    )
    add_section(
        embed,
        f"{E_INCOME} Заробіток",
        [
            compact_kv("Чат", f"`{msg_str}` {curr} / `{eco['msg_cooldown']}с`"),
            compact_kv("Голосовий чат і реакції", f"`{eco['voice_earn']}`/хв • `{eco['reaction_earn']}` за реакцію"),
            compact_kv("Робота", f"`{eco['work_min']}-{eco['work_max']}` {curr} • `{work_modes.get(eco['work_type'], 'Обидва режими')}`"),
            compact_kv("Щоденна нагорода", f"`{eco['daily_amount']}` {curr} • серія `+{eco['daily_streak_bonus']}` • перевірка {'вкл' if eco['captcha_enabled'] else 'викл'}"),
        ],
    )
    add_section(
        embed,
        f"{E_STATS} Ризик і ліміти",
        [
            compact_kv("Пограбування", f"{_status_text(eco['rob_enabled'])} • шанс `{eco['rob_chance']}%` • штраф `{eco['rob_fine_percent']}%`"),
            compact_kv("Крайм", f"{_status_text(eco['crime_enabled'])} • КД `{fmt_duration(eco['crime_cooldown'])}` • бан `{fmt_duration(eco['crime_ban_duration'])}`"),
            compact_kv("Банк", f"ліміт `{eco['bank_base_limit']:,}` {curr} • +`{eco['bank_level_multiplier']:,}`/рівень"),
            compact_kv("Гемблінг", f"{_status_text(eco['gambling_enabled'])} • макс. ставка `{eco['gambling_max_bet']:,}` {curr}"),
        ],
    )
    add_section(
        embed,
        f"{E_BOOST} Довгі системи",
        [
            compact_kv("Фонд", f"{_status_text(eco.get('fund_enabled', False))} • ціль `{eco.get('fund_goal', 1000000):,}` {curr}"),
            compact_kv("Інфляція", f"{_status_text(eco.get('inflation_enabled', True))} • множник `{eco.get('inflation_multiplier', 1.0):.2f}x`"),
            compact_kv("Квести", f"{_status_text(eco.get('quests_enabled', True))} • daily `{eco.get('quests_daily_count', 3)}` • weekly `{eco.get('quests_weekly_count', 2)}`"),
            compact_kv("Відсоток банку", interest_text),
        ],
    )
    add_section(
        embed,
        f"{E_SHOP} Контент",
        [
            compact_kv("Мініігри", f"`{minigames_enabled}` активних"),
            compact_kv("Ролі магазину", f"`{shop_roles}`"),
            compact_kv("Аукціон", auction_channel),
            compact_kv("Захист від снайпу", f"`{eco.get('auction_anti_snipe_seconds', 30)}с`"),
            compact_kv("Мін. крок ставки", f"`{eco.get('auction_min_increment', 100):,}` {curr}"),
        ],
    )
    return embed


def build_category_embed(eco: dict, category: str) -> discord.Embed:
    curr = normalize_currency_emoji(eco.get("currency_emoji"))
    titles = {
        "general": f"{E_SETTING} Загальне",
        "passive": f"{E_INCOME} Пасивний дохід",
        "work": f"{E_WORK} Робота",
        "daily": f"{E_DAILY} Щоденна нагорода",
        "bank": f"{E_BANK} Банк",
        "rob": f"{E_ROB} Пограбування",
        "crime": f"{E_CRIME} Крайм",
        "gambling": f"{E_STATS} Гемблінг",
        "shop": f"{E_SHOP} Магазин",
        "auction": f"{E_AUCTION} Аукціон",
        "games": f"{E_GAME} Налаштування ігор",
        "quests": f"{E_CLIPBOARD} Квести",
        "season": f"{E_TROPHY} Сезон",
        "transfers": f"{E_TRANSFER} Перекази",
    }
    embed = discord.Embed(title=titles.get(category, "Налаштування"), color=EMBED_COLOR)

    if category == "general":
        status_str = f"{E_CHECK} Увімкнена" if eco["enabled"] else f"{E_CROSS} Вимкнена"
        embed.description = (
            f"**Статус економіки:** {status_str}\n"
            f"**Валюта:** {curr} `{eco['currency_name']}`\n\n"
            f"**Фонд сервера:** {'ВКЛ' if eco.get('fund_enabled', False) else 'ВИКЛ'}\n"
            f"Мета фонду: `{eco.get('fund_goal', 1000000):,}` {curr}\n"
            f"Зібрано: `{eco.get('fund_current', 0):,}` {curr}\n\n"
            f"**Інфляція та твіки:**\n"
            f"Глобальна інфляція: {'ВКЛ' if eco.get('inflation_enabled', True) else 'ВИКЛ'}\n"
            f"Ліміт інфляції: `{eco.get('inflation_max_limit', 3.0):.1f}x` | Поточна: `{eco.get('inflation_multiplier', 1.0):.2f}x`\n"
            f"Мін. вік акаунта: `{eco.get('account_age_min_days', 14)} днів`\n"
            f"Податок переказу: `{eco.get('transfer_tax_percent', 0)}%` | Ліміт: `{eco.get('transfer_daily_limit', 0):,}` {curr}"
        )
    elif category == "passive":
        msg_earn = eco["msg_earn"]
        msg_str = f"{msg_earn[0]}-{msg_earn[1]}" if isinstance(msg_earn, list) else str(msg_earn)
        embed.description = (
            f"{E_CHAT} **Чат:** `{msg_str}` {curr} | КД: `{eco['msg_cooldown']}с`\n"
            f"{E_MICRO} **Голосовий чат:** `{eco['voice_earn']}` {curr}/хв\n"
            f"{E_STAR} **Реакції:** `{eco['reaction_earn']}` {curr}"
        )
    elif category == "work":
        work_modes = {"simple": "Лише легка", "complex": "Лише складна", "both": "Обидва"}
        embed.description = (
            f"{E_INCOME} **Сума:** `{eco['work_min']}-{eco['work_max']}` {curr}\n"
            f"{E_CLOCK} **КД:** `{fmt_duration(eco['work_cooldown'])}`\n"
            f"**Режим:** `{work_modes.get(eco['work_type'], 'Обидва')}`\n"
            f"{E_RANDOM} **Шанс події:** `{eco['event_chance']}%` | Ставка: `{eco['event_stake_percent']}%`\n"
            f"**Таймер події:** `{eco['event_timer']}с`\n"
            f"**Етапів у складній:** `{eco.get('work_complex_stages', 3)}` шт"
        )
    elif category == "daily":
        embed.description = (
            f"{E_INCOME} **Сума:** `{eco['daily_amount']}` {curr}\n"
            f"{E_FLAME} **Бонус за серію:** `+{eco['daily_streak_bonus']}` {curr}/день\n"
            f"{E_CLOCK} **КД:** `{fmt_duration(eco['daily_cooldown'])}`\n"
            f"**Перевірка:** {E_CHECK + ' Увімкнена' if eco['captcha_enabled'] else E_CROSS + ' Вимкнена'}"
        )
    elif category == "bank":
        rate_str = f"{eco['bank_interest_rate']}%" if eco.get("bank_interest_rate", 0) > 0 else "вимк"
        intv_str = "щодня" if eco.get("bank_interest_interval") == "daily" else "щотижня"
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
            f"{E_INCOME} **Крадіжка від балансу:** `{eco.get('rob_percent_min', 10)}-{eco.get('rob_percent_max', 40)}%`\n"
            f"{E_WARN} **Штраф при провалі:** `{eco['rob_fine_percent']}%`\n"
            f"{E_SHIELD} **Мін. баланс жертви:** `{eco['rob_min_balance_percent']}%`\n"
            f"{E_CLOCK} **Час вистежування:** `{eco['rob_time']}с`"
        )
    elif category == "crime":
        crime_str = f"{E_CHECK} Увімкнено" if eco["crime_enabled"] else f"{E_CROSS} Вимкнено"
        embed.description = (
            f"**Статус:** {crime_str}\n"
            f"{E_CLOCK} **КД:** `{fmt_duration(eco['crime_cooldown'])}`\n"
            f"{E_WARN} **Бан-штраф:** `{fmt_duration(eco['crime_ban_duration'])}`\n"
            f"{E_WALLET} **Хабар (% від куша):** `{eco.get('crime_bribe_percent', 75)}%`\n"
            f"{E_CLOCK} **Час на рішення:** `{eco.get('crime_bribe_timeout', 15)}с`"
        )
    elif category == "gambling":
        gamb_str = f"{E_CHECK} Увімкнено" if eco["gambling_enabled"] else f"{E_CROSS} Вимкнено"
        duel_timer = eco.get("duel_timer", 15)
        duel_max = eco.get("duel_max_rounds", 9)
        gambling_cd = eco.get("gambling_cooldown", 0)
        duel_en = f"{E_CHECK} Увімкнено" if eco.get("duel_enabled", True) else f"{E_CROSS} Вимк."
        draw_refund = eco.get("duel_draw_refund", True)
        draw_str = f"{E_CHECK} Повертаються" if draw_refund else f"{E_CROSS} Згорають"
        rtp_str = f"{eco.get('casino_rtp', 95)}%"
        cap_str = f"{eco.get('gambling_daily_cap', 0):,} {curr}" if eco.get("gambling_daily_cap", 0) > 0 else "вимк"
        embed.description = (
            f"{E_SLOTS} **Казино:** {gamb_str} • **Макс. ставка:** `{eco['gambling_max_bet']:,}` {curr}\n"
            f"**RTP:** `{rtp_str}` • **Ліміт/день:** `{cap_str}`\n"
            f"{E_CLOCK} **КД між ставками:** `{gambling_cd}с`\n"
            f"{E_SWORDS} **Дуелі:** {duel_en}\n"
            f"{E_CLOCK} Таймер ходу: `{duel_timer}с`\n"
            f"{E_SWORDS} Ліміт раундів: `{duel_max}`\n"
            f"{E_MINUS} При нічиї ставки: {draw_str}"
        )
    elif category == "shop":
        prices = {
            "Щит": eco.get("shop_shield_price", 5000),
            "Буст монет": eco.get("shop_xp_boost_price", 2000),
            "Перепустка для крайму": eco.get("shop_crime_pass_price", 3000),
        }
        lines = []
        for name, price in prices.items():
            status = f"`{price:,}` {curr}" if price > 0 else f"{E_CROSS} Вимкнено"
            lines.append(f"**{name}:** {status}")

        embed.description = (
            "\n".join(lines)
            + "\n\n"
            + f"**Лутбокси**\n"
            + f"{_E.LOOTBOX.value} Звичайний `{eco.get('shop_lootbox_common_price', 2500)}` {curr} | Джекпот: `{eco.get('lb_com_jackpot_pct', 10)}%`\n"
            + f"{_E.GIFT.value} Рідкісний `{eco.get('shop_lootbox_rare_price', 10000)}` {curr} | Джекпот: `{eco.get('lb_rare_jackpot_pct', 5)}%` | Pass: `{eco.get('lb_rare_pass_pct', 10)}%`"
        )
    elif category == "transfers":
        tax = eco.get("transfer_tax_percent", 0)
        lim = eco.get("transfer_daily_limit", 0)
        tax_str = f"`{tax}%` (знімається при кожному переказі)" if tax > 0 else f"{E_CROSS} Вимкнено"
        lim_str = f"`{lim:,}` {curr} (скидається о 00:00)" if lim > 0 else f"{E_CROSS} Вимкнено"
        embed.description = (
            f"**Податок на переказ:** {tax_str}\n"
            f"**Ліміт переказів/день:** {lim_str}"
        )
    elif category == "quests":
        q_enabled = eco.get("quests_enabled", True)
        q_status = f"{E_CHECK} Увімкнено" if q_enabled else f"{E_CROSS} Вимкнено"
        embed.description = (
            f"**Статус:** {q_status}\n"
            f"**Денних квестів:** `{eco.get('quests_daily_count', 3)}` шт • нагорода `{eco.get('quests_daily_reward', 200):,}` {curr}\n"
            f"**Тижневих квестів:** `{eco.get('quests_weekly_count', 2)}` шт • нагорода `{eco.get('quests_weekly_reward', 800):,}` {curr}"
        )
    elif category == "season":
        s_enabled = eco.get("season_enabled", False)
        s_status = f"{E_CHECK} Увімкнено" if s_enabled else f"{E_CROSS} Вимкнено"
        s_dur = eco.get("season_duration_days", 30)
        s_bonus = eco.get("season_start_bonus", 0)
        s_start = eco.get("season_start", 0)
        s_num = eco.get("season_number", 1)
        next_reset = s_start + s_dur * 86400 if s_start > 0 else None
        next_str = f"<t:{next_reset}:R>" if next_reset else "не запущено"

        winner_roles = eco.get("season_winner_roles", {})
        roles_lines = []
        for pos in ("1", "2", "3", "4", "5"):
            rid = winner_roles.get(pos)
            val = f"<@&{rid}>" if rid else f"{E_CROSS} не задано"
            roles_lines.append(f"  **{pos}.** {val}")
        roles_str = "\n".join(roles_lines) if roles_lines else f"{E_CROSS} Ролі не налаштовані"

        ch_id = eco.get("season_announce_channel_id", 0)
        ch_str = f"<#{ch_id}>" if ch_id else f"{E_CROSS} Вимкнено (не задано)"

        embed.description = (
            f"**Статус:** {s_status} • **Сезон:** #{s_num}\n"
            f"**Тривалість:** `{s_dur} днів`\n"
            f"**Стартовий бонус:** `{s_bonus:,}` {curr}\n"
            f"**Наступне скидання:** {next_str}\n\n"
            f"**Канал анонсу:**\n  {ch_str}\n\n"
            f"**Ролі переможців:**\n{roles_str}"
        )
    elif category == "auction":
        auc_channel = f"<#{eco['auction_channel_id']}>" if eco.get("auction_channel_id", 0) > 0 else f"{E_CROSS} Не встановлено"
        snipe_sec = eco.get("auction_anti_snipe_seconds", 30)
        min_increment = eco.get("auction_min_increment", 100)
        step_presets = eco.get("auction_step_presets", [100, 1000, 5000])
        steps_str = ", ".join(f"`+{int(step):,}`" for step in step_presets if isinstance(step, int) or str(step).isdigit()) or "`+100`, `+1,000`, `+5,000`"
        embed.description = (
            f"**Канал аукціону:** {auc_channel}\n"
            f"**Антиснайп:** `{snipe_sec}с`\n"
            f"**Мінімальний крок:** `{min_increment:,}` {curr}\n"
            f"**Кнопки підвищення:** {steps_str}\n\n"
            "Лоти додаються в чергу окремо, а запуск у канал робиться вручну через керування чергою."
        )
    elif category == "games":
        enabled = eco.get("enabled_minigames", ["math", "higher_lower", "shell", "dice", "odd_emoji", "unscramble", "trivia", "typing", "guess", "reaction"])
        embed.description = (
            f"**Увімкнено мініігор:** `{len(enabled)}/10`"
        )

    return embed
