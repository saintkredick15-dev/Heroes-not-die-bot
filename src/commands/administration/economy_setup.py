import discord
from discord import app_commands
from discord.ext import commands
from commands.administration.economy_setup_extras import (
    AuctionAddLotModal,
    AuctionChannelSelect,
    AuctionConfigModal,
    AuctionManageView,
    SeasonAnnounceChannelSelect,
    SeasonRolePositionSelect,
    ShopRolesView,
    build_shop_roles_embed,
)
from commands.administration import economy_setup_shared as _shared

E_AUCTION = _shared.E_AUCTION
E_BANK = _shared.E_BANK
E_BOOST = _shared.E_BOOST
E_CHECK = _shared.E_CHECK
E_CLIPBOARD = _shared.E_CLIPBOARD
E_CLOCK = _shared.E_CLOCK
E_CRIME = _shared.E_CRIME
E_CROSS = _shared.E_CROSS
E_DAILY = _shared.E_DAILY
E_FLAME = _shared.E_FLAME
E_HELP = _shared.E_HELP
E_INCOME = _shared.E_INCOME
E_LEFT = _shared.E_LEFT
E_MINUS = _shared.E_MINUS
E_RANDOM = _shared.E_RANDOM
E_ROB = _shared.E_ROB
E_ROLE = _shared.E_ROLE
E_SETTING = _shared.E_SETTING
E_SHIELD = _shared.E_SHIELD
E_SHOP = _shared.E_SHOP
E_SLOTS = _shared.E_SLOTS
E_STAR = _shared.E_STAR
E_STATS = _shared.E_STATS
E_SWORDS = _shared.E_SWORDS
E_TRANSFER = _shared.E_TRANSFER
E_TROPHY = _shared.E_TROPHY
E_WALLET = _shared.E_WALLET
E_WORK = _shared.E_WORK
EMBED_COLOR = _shared.EMBED_COLOR
build_category_embed = _shared.build_category_embed
build_main_embed = _shared.build_main_embed
db = _shared.db
fmt_duration = _shared.fmt_duration
fmt_duration_modal = _shared.fmt_duration_modal
get_eco = _shared.get_eco
parse_duration = _shared.parse_duration
save_eco = _shared.save_eco
normalize_currency_emoji = _shared.normalize_currency_emoji

class GeneralModal(discord.ui.Modal, title=f"{E_SETTING} Загальні налаштування"):
    currency_name  = discord.ui.TextInput(label="Назва валюти", max_length=30)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.currency_name.default  = eco["currency_name"]

    async def on_submit(self, interaction: discord.Interaction):
        updates = {
            "economy.currency_name":  self.currency_name.value.strip(),
        }
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        embed = build_category_embed(self.main_view.eco, "general")
        cat_view = SetupCategoryView(self.main_view, "general")
        await interaction.response.edit_message(embed=embed, view=cat_view)

class PassiveModal(discord.ui.Modal, title=f"{E_INCOME} Пасивний дохід"):
    msg_earn    = discord.ui.TextInput(label="Чат (мін-макс, напр. 5-10)", max_length=10)
    msg_cd      = discord.ui.TextInput(label="КД чату (секунди)", max_length=6)
    voice_earn  = discord.ui.TextInput(label="Голосовий чат (за хвилину)", max_length=5)
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

class WorkAmountModal(discord.ui.Modal, title=f"{E_WORK} Work — Сума"):
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

class WorkCooldownModal(discord.ui.Modal, title=f"{E_CLOCK} Work — Кулдаун"):
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

class WorkEventModal(discord.ui.Modal, title=f"{E_RANDOM} Work — Налаштування події"):
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

class DailyAmountModal(discord.ui.Modal, title=f"{E_DAILY} Щоденна нагорода — сума"):
    amount  = discord.ui.TextInput(label="Базова сума", max_length=10)
    streak  = discord.ui.TextInput(label="Бонус за серію на день", max_length=10)

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

class DailyCooldownModal(discord.ui.Modal, title=f"{E_CLOCK} Щоденна нагорода — кулдаун"):
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

class BankModal(discord.ui.Modal, title=f"{E_BANK} Банк"):
    base_limit    = discord.ui.TextInput(label="Базовий ліміт", max_length=10)
    lvl_mult      = discord.ui.TextInput(label="Множник за рівень", max_length=10)
    interest_rate = discord.ui.TextInput(label="Відсоток % (напр. 1.5, 0=вимк)", max_length=5)
    interest_intv = discord.ui.TextInput(label="Період: день або тиждень", max_length=6)

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

class RobModal(discord.ui.Modal, title=f"{E_ROB} Пограбування Основне"):
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

class RobAdvancedModal(discord.ui.Modal, title=f"{E_ROB} Пограбування Додатково"):
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

class CrimeModal(discord.ui.Modal, title=f"{E_CRIME} Крайм"):
    cooldown      = discord.ui.TextInput(label="КД (напр. 8h)", max_length=10)
    ban_duration  = discord.ui.TextInput(label="Бан при провалі (напр. 30m)", max_length=10)
    bribe_percent = discord.ui.TextInput(label="% хабаря від куша", max_length=5)
    bribe_timeout = discord.ui.TextInput(label="Час на хабар (с)", max_length=4)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.cooldown.default      = fmt_duration_modal(eco["crime_cooldown"])
        self.ban_duration.default  = fmt_duration_modal(eco["crime_ban_duration"])
        self.bribe_percent.default = str(eco.get("crime_bribe_percent", 75))
        self.bribe_timeout.default = str(eco.get("crime_bribe_timeout", 15))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.crime_cooldown":      parse_duration(self.cooldown.value),
                "economy.crime_ban_duration":  parse_duration(self.ban_duration.value),
                "economy.crime_bribe_percent": int(self.bribe_percent.value),
                "economy.crime_bribe_timeout": int(self.bribe_timeout.value),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Формат: `8h`, `30m` або числа для %.", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "crime"),
            view=SetupCategoryView(self.main_view, "crime")
        )

class GamblingModal(discord.ui.Modal, title=f"{E_SLOTS} Гемблінг"):
    max_bet    = discord.ui.TextInput(label="Максимальна ставка", max_length=10)
    duel_timer = discord.ui.TextInput(label="Таймер дуелі (секунди)", max_length=4)
    max_rounds = discord.ui.TextInput(label="Ліміт раундів дуелі", max_length=3)
    casino_rtp = discord.ui.TextInput(label="Casino RTP % (0-100, 95=стандарт)", max_length=3)
    daily_cap  = discord.ui.TextInput(label="Ліміт виграшу/день (0=вимк)", max_length=10)
    cooldown   = discord.ui.TextInput(label="Кулдаун між ставками сек (0=вимк)", max_length=6)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.max_bet.default    = str(eco["gambling_max_bet"])
        self.duel_timer.default = str(eco.get("duel_timer", 15))
        self.max_rounds.default = str(eco.get("duel_max_rounds", 9))
        self.casino_rtp.default = str(eco.get("casino_rtp", 95))
        self.daily_cap.default  = str(eco.get("gambling_daily_cap", 0))
        self.cooldown.default   = str(eco.get("gambling_cooldown", 0))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.gambling_max_bet":   int(self.max_bet.value),
                "economy.duel_timer":         int(self.duel_timer.value),
                "economy.duel_max_rounds":    int(self.max_rounds.value),
                "economy.casino_rtp":         max(0, min(100, int(self.casino_rtp.value))),
                "economy.gambling_daily_cap": int(self.daily_cap.value),
                "economy.gambling_cooldown":  max(0, int(self.cooldown.value)),
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

class ShopPricesModal(discord.ui.Modal, title=f"{E_SHOP} Ціни магазину"):
    shield     = discord.ui.TextInput(label="Щит (0 = вимк)", max_length=10)
    xp_boost   = discord.ui.TextInput(label="XP Буст (0 = вимк)", max_length=10)
    lottery    = discord.ui.TextInput(label="Лото квиток (0 = вимк)", max_length=10)
    crime_pass = discord.ui.TextInput(label="Перепустка для крайму (0 = вимк)", max_length=10)

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
            discord.SelectOption(label="Щоденна нагорода", value="daily",   description="Нагорода, серія, перевірка",          emoji=discord.PartialEmoji.from_str(E_DAILY)),
            discord.SelectOption(label="Банк",            value="bank",     description="Ліміти та множники",                   emoji=discord.PartialEmoji.from_str(E_BANK)),
            discord.SelectOption(label="Пограбування",   value="rob",      description="Шанс, штраф, мін. баланс",             emoji=discord.PartialEmoji.from_str(E_ROB)),
            discord.SelectOption(label="Крайм",          value="crime",    description="КД та штраф-бан",                     emoji=discord.PartialEmoji.from_str(E_CRIME)),
            discord.SelectOption(label="Ігри та Казино", value="gambling",  description="Казино, Дуелі та Міні-ігри роботи",     emoji=discord.PartialEmoji.from_str(E_STATS)),
            discord.SelectOption(label="Магазин",        value="shop",      description="Ціни системних предметів",             emoji=discord.PartialEmoji.from_str(E_SHOP)),
            discord.SelectOption(label="Аукціон",        value="auction",   description="Канал, лоти та черга",                 emoji=discord.PartialEmoji.from_str(E_AUCTION)),
            discord.SelectOption(label="Квести",         value="quests",    description="Налаштування денних/тижневих завдань", emoji=discord.PartialEmoji.from_str(E_HELP)),
        ]
        super().__init__(placeholder="Оберіть блок економіки для редагування...", options=options)

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
        super().__init__(placeholder="Оберіть міні-ігри для легкої роботи...", min_values=1, max_values=10, options=options)

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

            self._add("Валюта та ядро", discord.ButtonStyle.secondary, self._general_cb)
            self._add("Перекази", discord.ButtonStyle.secondary, self._transfer_cb)
            self._add("Інфляція та твіни", discord.ButtonStyle.secondary, self._inflation_cb)
            
            f_enabled = eco.get("fund_enabled", False)
            fb = discord.ui.Button(label="Фонд: ВКЛ" if f_enabled else "Фонд: ВИКЛ", style=discord.ButtonStyle.success if f_enabled else discord.ButtonStyle.secondary)
            fb.callback = lambda i: self._toggle_bool(i, "economy.fund_enabled", not f_enabled, "general")
            self.add_item(fb)
            
            self._add("Ціль фонду", discord.ButtonStyle.secondary, self._fund_modal_cb)
            self._add("Параметри сезону", discord.ButtonStyle.secondary, self._season_cb)
            
            reset_btn = discord.ui.Button(label="Сезонний ресет зараз", style=discord.ButtonStyle.secondary, row=1)
            reset_btn.callback = self._season_reset_now
            self.add_item(reset_btn)

        elif category == "passive":
            self._add("Суми та кулдауни", discord.ButtonStyle.secondary, self._passive_cb)

        elif category == "work":
            self._add("Сума заробітку",       discord.ButtonStyle.secondary, self._work_amount_cb)
            self._add("Кулдаун",              discord.ButtonStyle.secondary, self._work_cd_cb)
            self._add("Подія та ризик",   discord.ButtonStyle.secondary, self._work_event_cb)
            
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
            cap_label = "Перевірка: ВКЛ" if eco["captcha_enabled"] else "Перевірка: ВИКЛ"
            b = discord.ui.Button(label=cap_label, style=cap_style, row=1)
            b.callback = self._toggle_captcha
            self.add_item(b)

        elif category == "bank":
            self._add("Ліміти та відсоток", discord.ButtonStyle.secondary, self._bank_cb)

        elif category == "rob":
            rob_style = discord.ButtonStyle.success if eco["rob_enabled"] else discord.ButtonStyle.secondary
            rob_label = "Пограбування: ВКЛ" if eco["rob_enabled"] else "Пограбування: ВИКЛ"
            b = discord.ui.Button(label=rob_label, style=rob_style)
            b.callback = lambda i: self._toggle_bool(i, "economy.rob_enabled", not eco["rob_enabled"], "rob")
            self.add_item(b)
            self._add("Шанс, штраф і таймер", discord.ButtonStyle.secondary, self._rob_cb)
            self._add("Відсоток крадіжки та КД", discord.ButtonStyle.secondary, self._rob_adv_cb)

        elif category == "crime":
            crime_style = discord.ButtonStyle.success if eco["crime_enabled"] else discord.ButtonStyle.secondary
            crime_label = "Крайм: ВКЛ" if eco["crime_enabled"] else "Крайм: ВИКЛ"
            b = discord.ui.Button(label=crime_label, style=crime_style)
            b.callback = lambda i: self._toggle_bool(i, "economy.crime_enabled", not eco["crime_enabled"], "crime")
            self.add_item(b)
            self._add("КД, бан і хабар", discord.ButtonStyle.secondary, self._crime_cb)

        elif category == "gambling":
            gamb_style = discord.ButtonStyle.success if eco["gambling_enabled"] else discord.ButtonStyle.secondary
            gamb_label = "Казино & Ігри: ВКЛ" if eco["gambling_enabled"] else "Казино & Ігри: ВИКЛ"
            b = discord.ui.Button(label=gamb_label, style=gamb_style)
            b.callback = lambda i: self._toggle_bool(i, "economy.gambling_enabled", not eco["gambling_enabled"], "gambling")
            self.add_item(b)
            
            self._add("Ставки, RTP і ліміти", discord.ButtonStyle.secondary, self._gambling_cb)
            
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
            self._add("Лутбокси", discord.ButtonStyle.secondary, self._lootboxes_cb)
            
            roles_btn = discord.ui.Button(label="Кастомні ролі магазину", style=discord.ButtonStyle.primary, emoji=discord.PartialEmoji.from_str(E_ROLE))
            roles_btn.callback = self._shop_roles_cb
            self.add_item(roles_btn)

        elif category == "quests":
            q_enabled = eco.get("quests_enabled", True)
            q_style   = discord.ButtonStyle.success if q_enabled else discord.ButtonStyle.secondary
            q_label   = "Квести: ВКЛ" if q_enabled else "Квести: ВИКЛ"
            qb = discord.ui.Button(label=q_label, style=q_style)
            qb.callback = lambda i: self._toggle_bool(i, "economy.quests_enabled", not q_enabled, "quests")
            self.add_item(qb)
            self._add("Нагороди та множник", discord.ButtonStyle.secondary, self._quests_cb)

        elif category == "season":
            # ── Toggle сезону ──────────────────────────────────────────────────
            s_enabled = eco.get("season_enabled", False)
            sb = discord.ui.Button(
                label="Сезон: ВКЛ" if s_enabled else "Сезон: ВИКЛ",
                style=discord.ButtonStyle.success if s_enabled else discord.ButtonStyle.secondary
            )
            sb.callback = lambda i: self._toggle_bool(i, "economy.season_enabled", not s_enabled, "season")
            self.add_item(sb)
            # ── Modal (тривалість + бонус) ─────────────────────────────────────
            self._add("Тривалість та бонус", discord.ButtonStyle.secondary, self._season_cb)
            # ── Вибір каналу анонсу ────────────────────────────────────────────
            self.add_item(SeasonAnnounceChannelSelect(self.main_view, eco))
            # ── Ролі переможців (select позиції → RoleSelect) ──────────────────
            self.add_item(SeasonRolePositionSelect(self.main_view, eco))

        elif category == "auction":
            self.add_item(AuctionChannelSelect(self.main_view))
            self._add("Захист від снайпу", discord.ButtonStyle.secondary, self._auction_config_cb)
            
            add_lot_btn = discord.ui.Button(label="Додати лот", style=discord.ButtonStyle.primary, emoji=discord.PartialEmoji.from_str(_E.PLUS.value))
            add_lot_btn.callback = self._auction_add_lot_cb
            self.add_item(add_lot_btn)
            
            manage_lot_btn = discord.ui.Button(label="Черга лотів", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_CLIPBOARD))
            manage_lot_btn.callback = self._auction_manage_cb
            self.add_item(manage_lot_btn)

        back = discord.ui.Button(
            label="Назад",
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
        class WorkStagesModal(discord.ui.Modal, title=f"{E_WORK} Work — Етапи складної"):
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
    async def _lootboxes_cb(self, i): await i.response.send_modal(LootboxesModal(self.main_view, self.main_view.eco))
    
    async def _shop_roles_cb(self, interaction: discord.Interaction):
        
        await interaction.response.edit_message(
            embed=build_shop_roles_embed(self.main_view.eco, interaction.guild),
            view=ShopRolesView(self.main_view, interaction.guild)
        )
        
    async def _games_cb(self, i):     await i.response.send_modal(GamesModal(self.main_view, self.main_view.eco))
    async def _transfer_cb(self, i):  await i.response.send_modal(TransferModal(self.main_view, self.main_view.eco))
    async def _inflation_cb(self, i): await i.response.send_modal(InflationModal(self.main_view, self.main_view.eco))
    async def _fund_modal_cb(self, i):
        class FundModal(discord.ui.Modal, title="Налаштування Фонду"):
            goal = discord.ui.TextInput(label="Ціль збору (число)", max_length=15)
            curr = discord.ui.TextInput(label="Вже зібрано (за потреби)", max_length=15)
            def __init__(self, mv):
                super().__init__()
                self.mv = mv
                self.goal.default = str(mv.eco.get("fund_goal", 1000000))
                self.curr.default = str(mv.eco.get("fund_current", 0))
            async def on_submit(self, interaction: discord.Interaction):
                try:
                    g = max(1, int(self.goal.value))
                    c = max(0, int(self.curr.value))
                    await save_eco(interaction.guild.id, {"economy.fund_goal": g, "economy.fund_current": c})
                    ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
                    self.mv.eco = get_eco(ctx)
                    await interaction.response.edit_message(
                        embed=build_category_embed(self.mv.eco, "general"),
                        view=SetupCategoryView(self.mv, "general")
                    )
                except ValueError:
                    await interaction.response.send_message("Лише числа!", ephemeral=True)
        await i.response.send_modal(FundModal(self.main_view))

    async def _quests_cb(self, i):    await i.response.send_modal(QuestsModal(self.main_view, self.main_view.eco))
    async def _season_cb(self, i):    await i.response.send_modal(SeasonModal(self.main_view, self.main_view.eco))
    async def _auction_config_cb(self, i): await i.response.send_modal(AuctionConfigModal(self.main_view, self.main_view.eco))
    async def _auction_add_lot_cb(self, i): await i.response.send_modal(AuctionAddLotModal(self.main_view))
    
    async def _auction_manage_cb(self, interaction: discord.Interaction):
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        queue = ctx.get("auction_queue", [])
        
        if not queue:
            return await interaction.response.send_message(f"{E_CROSS} Черга лотів порожня. Додайте спочатку лоти.", ephemeral=True)
            
        embed = discord.Embed(
            title=f"{E_CLIPBOARD} Керування чергою Аукціону",
            description=f"В черзі зараз лотів: **{len(queue)}**\nВиберіть лот у списку нижче, щоб запустити його або видалити.",
            color=EMBED_COLOR
        )
        await interaction.response.edit_message(embed=embed, view=AuctionManageView(self.main_view, queue))

    async def _season_reset_now(self, interaction: discord.Interaction):
        
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

class LootboxesModal(discord.ui.Modal, title="Налаштування Лутбоксів"):
    cp = discord.ui.TextInput(label="Ціна: Звичайний", max_length=10)
    cj = discord.ui.TextInput(label="Шанс Джекпоту (Звичайний) %", max_length=3)
    rp = discord.ui.TextInput(label="Ціна: Рідкісний", max_length=10)
    rj = discord.ui.TextInput(label="Шанс Джекпоту (Рідкісний) %", max_length=3)
    r_pass = discord.ui.TextInput(label="Шанс перепустки для крайму (рідкісна) %", max_length=3)

    def __init__(self, mv, eco: dict):
        super().__init__()
        self.mv = mv
        self.cp.default = str(eco.get("shop_lootbox_common_price", 2500))
        self.cj.default = str(eco.get("lb_com_jackpot_pct", 10))
        self.rp.default = str(eco.get("shop_lootbox_rare_price", 10000))
        self.rj.default = str(eco.get("lb_rare_jackpot_pct", 5))
        self.r_pass.default = str(eco.get("lb_rare_pass_pct", 10))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cp = max(1, int(self.cp.value))
            cj = min(100, max(0, int(self.cj.value)))
            rp = max(1, int(self.rp.value))
            rj = min(100, max(0, int(self.rj.value)))
            r_pass = min(100, max(0, int(self.r_pass.value)))
            
            p = {
                "economy.shop_lootbox_common_price": cp,
                "economy.lb_com_jackpot_pct": cj,
                "economy.shop_lootbox_rare_price": rp,
                "economy.lb_rare_jackpot_pct": rj,
                "economy.lb_rare_pass_pct": r_pass
            }
            await save_eco(interaction.guild.id, p)
            await self.mv._update("shop", interaction)
        except ValueError:
            await interaction.response.send_message("Лише цілі числа!", ephemeral=True)

class TransferModal(discord.ui.Modal, title=f"{E_TRANSFER} Перекази"):
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
            embed=build_category_embed(self.main_view.eco, "general"),
            view=SetupCategoryView(self.main_view, "general")
        )

class InflationModal(discord.ui.Modal, title=f"{E_STATS} Інфляція та Твінки"):
    inf_lim = discord.ui.TextInput(label="Ліміт Інфляції (х, напр. 3.0)", max_length=5)
    age_min = discord.ui.TextInput(label="Мін. вік акаунта (днів, 0=вимк)", max_length=4)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.inf_lim.default = str(eco.get("inflation_max_limit", 3.0))
        self.age_min.default = str(eco.get("account_age_min_days", 14))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.inflation_max_limit": float(self.inf_lim.value),
                "economy.account_age_min_days": int(self.age_min.value),
            }
        except ValueError:
            await interaction.response.send_message(f"Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, updates)
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "general"),
            view=SetupCategoryView(self.main_view, "general")
        )

class QuestsModal(discord.ui.Modal, title=f"{E_CLIPBOARD} Квести"):
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

class SeasonModal(discord.ui.Modal, title=f"{E_TROPHY} Сезон"):
    duration    = discord.ui.TextInput(label="Тривалість сезону (днів)", max_length=4)
    start_bonus = discord.ui.TextInput(label="Стартовий бонус монет (0=без бонусу)", max_length=10)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.duration.default    = str(eco.get("season_duration_days", 30))
        self.start_bonus.default = str(eco.get("season_start_bonus", 0))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            updates = {
                "economy.season_duration_days": max(1, int(self.duration.value)),
                "economy.season_start_bonus":   max(0, int(self.start_bonus.value)),
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

class EconomySetup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="economy_setup", description="[Admin] Налаштувати серверну економіку")
    @app_commands.default_permissions(administrator=True)
    async def economy_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from modules.db import get_guild_settings
        settings = await get_guild_settings(db, interaction.guild.id)
        eco = get_eco(settings)
        embed = build_main_embed(eco)
        view  = EcoSetupView(eco)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(EconomySetup(bot))
