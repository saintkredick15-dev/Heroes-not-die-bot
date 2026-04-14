import time as _time
from datetime import datetime, timedelta, timezone
from config.constants import Emojis

ECONOMY_DAILY_EARNINGS_FIELD = "economy_daily_earnings"

def make_log(amount: int, desc: str) -> dict:
    
    now   = int(_time.time())
    color = Emojis.PLUS.value if amount >= 0 else Emojis.MINUS.value
    return {"log": f"{color} **{abs(amount)}** | {desc} | <t:{now}:t>"}


def utc_day_key(timestamp: int | None = None) -> str:
    raw = _time.time() if timestamp is None else timestamp
    return datetime.fromtimestamp(raw, tz=timezone.utc).strftime("%Y-%m-%d")


def add_daily_earnings_inc(
    inc_query: dict,
    amount: int,
    *,
    timestamp: int | None = None,
    field: str = ECONOMY_DAILY_EARNINGS_FIELD,
) -> None:
    if amount <= 0:
        return

    key = f"{field}.{utc_day_key(timestamp)}"
    inc_query[key] = inc_query.get(key, 0) + int(amount)


def sum_recent_daily_earnings(
    doc: dict,
    days: int,
    *,
    timestamp: int | None = None,
    field: str = ECONOMY_DAILY_EARNINGS_FIELD,
) -> int:
    if days <= 0:
        return 0

    history = doc.get(field, {})
    if not isinstance(history, dict):
        return 0

    raw = _time.time() if timestamp is None else timestamp
    today = datetime.fromtimestamp(raw, tz=timezone.utc).date()
    total = 0

    for offset in range(days):
        day_key = (today - timedelta(days=offset)).isoformat()
        value = history.get(day_key, 0)
        if isinstance(value, (int, float)):
            total += int(value)

    return total

def fmt_duration(seconds: int) -> str:
    # Форматування тривалості кулдауну в людський вигляд
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h and m: return f"{h}г {m}хв"
    if h: return f"{h}г"
    return f"{m}хв"

def fmt_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}г")
    if m:
        parts.append(f"{m}хв")
    if s and not h:
        parts.append(f"{s}с")
    return " ".join(parts) or "0с"


def calculate_tax(base_amount: int, wallet: int, bank: int) -> tuple[int, int, str]:
    # Рахуємо податок на багатство, щоб багатії не фармили занадто багато
    from config.constants import EcoOptions
    
    total_wealth = wallet + bank
    tax_pct = 0.0

    if total_wealth >= EcoOptions.TAX_BRACKET_4.value[0]:
        tax_pct = EcoOptions.TAX_BRACKET_4.value[1]
    elif total_wealth >= EcoOptions.TAX_BRACKET_3.value[0]:
        tax_pct = EcoOptions.TAX_BRACKET_3.value[1]
    elif total_wealth >= EcoOptions.TAX_BRACKET_2.value[0]:
        tax_pct = EcoOptions.TAX_BRACKET_2.value[1]
    elif total_wealth >= EcoOptions.TAX_BRACKET_1.value[0]:
        tax_pct = EcoOptions.TAX_BRACKET_1.value[1]

    if tax_pct > 0:
        tax_amount = int(base_amount * tax_pct)
        return max(0, base_amount - tax_amount), tax_amount, f"{int(tax_pct * 100)}%"
    
    return base_amount, 0, "0%"

async def check_account_age(interaction, eco: dict) -> bool:
    # Захист від твінків: якщо акаунту пару днів, не пускаємо в економіку
    import datetime
    from config.constants import EcoOptions

    min_days = eco.get("account_age_min_days", EcoOptions.ACCOUNT_AGE_MIN_DAYS.value)
    if min_days <= 0:
        return True

    account_created: datetime.datetime = interaction.user.created_at
    now = datetime.datetime.now(account_created.tzinfo)
    age = now - account_created

    if age.days < min_days:
        await interaction.response.send_message(
            f"<:close:1485598320935174317> Твій акаунт Discord занадто новий для використання економіки.\n"
            f"Мінімальний вік акаунта — **{min_days} днів** (залишилось ще {min_days - age.days} днів).",
            ephemeral=True
        )
        return False
    return True

async def apply_inflation(db, guild_id: int, generated_amount: int, eco_settings: dict = None):
    # Глобальне підвищення цін в магазині при друкарні грошей сервером
    if generated_amount <= 0: return
    if not eco_settings:
        from commands.administration.economy_setup_shared import get_eco
        from modules.db import get_guild_settings
        settings = await get_guild_settings(db, guild_id)
        eco_settings = get_eco(settings)
        
    if not eco_settings.get("inflation_enabled", True):
        return

    rate = 1.0 + (generated_amount / 1000.0) * 0.00001
    
    current_inflation_multiplier = eco_settings.get("inflation_multiplier", 1.0)
    
    from config.constants import EcoOptions
    max_inflation_limit = eco_settings.get("inflation_max_limit", EcoOptions.DEFAULT_INFLATION_LIMIT.value)
    
    if current_inflation_multiplier >= max_inflation_limit:
        return
        
    if current_inflation_multiplier * rate > max_inflation_limit:
        rate = max_inflation_limit / current_inflation_multiplier

    updates = {}
    
    shop_keys = [
        "shop_shield_price", "shop_xp_boost_price", 
        "shop_lootbox_common_price", "shop_lootbox_rare_price", 
        "shop_crime_pass_price"
    ]
    
    for key in shop_keys:
        curr_price = eco_settings.get(key)
        if curr_price is not None:
            new_price = int(curr_price * rate)
            if new_price > curr_price: 
                updates[f"economy.{key}"] = new_price

    shop_roles = eco_settings.get("shop_roles", [])
    if shop_roles:
        updated_roles = []
        for r in shop_roles:
            new_price = int(r["price"] * rate)
            
            r["price"] = new_price if new_price > r["price"] else r["price"]
            updated_roles.append(r)
        updates["economy.shop_roles"] = updated_roles
        
    updates["economy.inflation_multiplier"] = eco_settings.get("inflation_multiplier", 1.0) * rate

    if updates:
        await db.guild_settings.update_one(
            {"_id": guild_id},
            {"$set": updates},
            upsert=True
        )
