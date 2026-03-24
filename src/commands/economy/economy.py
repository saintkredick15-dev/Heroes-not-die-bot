import discord
from discord import app_commands
from discord.ext import commands
import time
import random
import math

from modules.db import get_database
from repositories.user import get_user
from commands.economy.events import ROB_STAGE_1, ROB_STAGE_2, ROB_STAGE_3
from commands.economy.quests import quest_hook
from utils.eco_helpers import make_log
from utils.ui_contract import add_section, compact_kv, gameplay_result_embed, set_surface_footer, surface_embed

db = get_database()

E_HISTORY = "<:history:1485601911599009893>"
E_ROBBERY = "<:mask:1485625427014713394>"
E_BACK    = "<:prevtotheleft:1485600254760980501>"
E_NEXT    = "<:nexttotheright:1485600703052517376>"
E_INBOX   = "<:inbox:1485599203815325836>"
E_CHECK   = "<:check:1485597845883981905>"
E_CROSS   = "<:close:1485598320935174317>"

class ValueModal(discord.ui.Modal):
    def __init__(self, owner_id: int, action: str, eco: dict, term: str = None):
        titles = {
            "deposit": f"💳 Депозит у банк" + (f" ({term})" if term else ""),
            "withdraw": "💸 Зняття з банку",
            "transfer": "↔️ Переказ коштів"
        }
        super().__init__(title=titles.get(action, "Операція"))
        self.owner_id = owner_id
        self.action = action
        self.eco = eco
        self.term = term

        if action == "transfer":
            self.target_id = discord.ui.TextInput(
                label="Discord ID отримувача",
                placeholder="123456789012345678",
                required=True,
                max_length=25
            )
            self.add_item(self.target_id)
            
        self.amount = discord.ui.TextInput(
            label="Сума (або 'all')",
            placeholder="100",
            required=True,
            max_length=15
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        wallet = user_data.get("wallet", 0)
        bank = user_data.get("bank", 0)
        level = user_data.get("level", 1)
        bank_limit = self.eco.get("bank_base_limit", 10000) + (self.eco.get("bank_level_multiplier", 1000) * level)
        currency = self.eco.get("currency_emoji", "<:coin:1485610808003133552>")

        val_str = self.amount.value.strip().lower()
        if val_str == 'all':
            if self.action in ["deposit", "transfer"]:
                amount = wallet
            else:
                amount = bank
        else:
            try:
                amount = int(val_str)
            except ValueError:
                return await interaction.response.send_message("<:close:1485598320935174317> Будь ласка, введіть число або 'all'.", ephemeral=True)

        if amount <= 0:
            return await interaction.response.send_message("<:close:1485598320935174317> Сума має бути більшою за нуль.", ephemeral=True)

        log_item = None
        if self.action == "deposit":
            if bank + amount > bank_limit:
                max_dep = bank_limit - bank
                if max_dep <= 0:
                    return await interaction.response.send_message("<:close:1485598320935174317> Ваш банк переповнений!", ephemeral=True)
                return await interaction.response.send_message(f"<:close:1485598320935174317> Ви не можете покласти стільки. Доступне місце: **{max_dep}** {currency}", ephemeral=True)
            
            desc = f"Депозит у банк" + (f" (Термін: {self.term})" if self.term else "")
            log_item = make_log(-amount, desc)
            
            result = await db.users.find_one_and_update(
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id, "wallet": {"$gte": amount}},
                {"$inc": {"wallet": -amount, "bank": amount}, "$push": {"eco_history": {"$each": [log_item], "$slice": -50}}}
            )
            
            if not result:
                return await interaction.response.send_message(f"<:close:1485598320935174317> Недостатньо коштів у гаманці. У вас: **{wallet}** {currency}", ephemeral=True)

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, interaction.user.id)

            await quest_hook(interaction.guild.id, interaction.user.id, "economy.deposit")
            await interaction.response.send_message(f"<:check:1485597845883981905> Ви успішно поклали **{amount}** {currency} у банк" + (f" на термін **{self.term}**" if self.term else "") + ".", ephemeral=True)

        elif self.action == "withdraw":
            log_item = make_log(amount, "Зняття з банку")
            
            result = await db.users.find_one_and_update(
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id, "bank": {"$gte": amount}},
                {"$inc": {"wallet": amount, "bank": -amount}, "$push": {"eco_history": {"$each": [log_item], "$slice": -50}}}
            )
            
            if not result:
                return await interaction.response.send_message(f"<:close:1485598320935174317> Недостатньо коштів у банку. У вас: **{bank}** {currency}", ephemeral=True)

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, interaction.user.id)

            await interaction.response.send_message(f"<:check:1485597845883981905> Ви успішно зняли **{amount}** {currency} з банку.", ephemeral=True)

        elif self.action == "transfer":
            # Анти-твінк захист: щоб малі рівні не перекидали віртуальну валюту туди-сюди
            from utils.eco_helpers import check_account_age
            if not await check_account_age(interaction, self.eco):
                return

            import time as _time
            tax_pct  = self.eco.get("transfer_tax_percent", 0)
            day_lim  = self.eco.get("transfer_daily_limit", 0)
            raw_id = self.target_id.value.strip()

            if not raw_id.isdigit():
                return await interaction.response.send_message("<:close:1485598320935174317> ID отримувача має складатися з цифр.", ephemeral=True)
            target_user_id = int(raw_id)

            if target_user_id == interaction.user.id:
                return await interaction.response.send_message("<:close:1485598320935174317> Не можна переказати кошти самому собі.", ephemeral=True)

            target_member = interaction.guild.get_member(target_user_id)
            if not target_member or target_member.bot:
                return await interaction.response.send_message("<:close:1485598320935174317> Неможливо знайти такого користувача.", ephemeral=True)

            tax_amount = math.ceil(amount * tax_pct / 100) if tax_pct > 0 else 0
            received   = amount - tax_amount
            if received <= 0:
                return await interaction.response.send_message(
                    f"<:close:1485598320935174317> Після податку переказ не залишає валідної суми для отримувача.",
                    ephemeral=True,
                )
            today      = _time.strftime("%Y-%m-%d")

            query_filter = {
                "guild_id": interaction.guild.id,
                "user_id": interaction.user.id,
                "wallet": {"$gte": amount},
            }
            if day_lim > 0:
                query_filter["$or"] = [
                    {"transfer_date": {"$ne": today}},
                    {"transfer_today": {"$lte": day_lim - amount}}
                ]

            sender_result = await db.users.find_one_and_update(
                query_filter,
                {
                    "$inc": {"wallet": -amount, "transfer_today": amount},
                    "$set": {"transfer_date": today},
                    "$push": {"eco_history": {
                        "$each": [make_log(-amount, f"Переказ для {target_member.display_name}" + (f" (tax {tax_pct}%)" if tax_amount else ""))],
                        "$slice": -50
                    }}
                }
            )
            if sender_result is None:
                today_sent = user_data.get("transfer_today", 0) if user_data.get("transfer_date") == today else 0
                remaining  = max(0, day_lim - today_sent) if day_lim > 0 else 0
                if day_lim > 0 and remaining < amount:
                    return await interaction.response.send_message(
                        f"<:close:1485598320935174317> Добовий ліміт переказів: `{day_lim:,}` {currency}. Залишилось: `{remaining:,}`", ephemeral=True
                    )
                return await interaction.response.send_message(f"<:close:1485598320935174317> Недостатньо коштів. У вас: **{wallet}** {currency}", ephemeral=True)

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, interaction.user.id)

            await get_user(db, interaction.guild.id, target_user_id)
            await db.users.update_one(
                {"guild_id": interaction.guild.id, "user_id": target_user_id},
                {"$inc": {"wallet": received}, "$push": {"eco_history": {
                    "$each": [make_log(received, f"Переказ від {interaction.user.display_name}")],
                    "$slice": -50
                }}}
            )
            await invalidate_user_data(interaction.guild.id, target_user_id)
            tax_msg = f" (податок: **{tax_amount}** {currency})" if tax_amount else ""
            await interaction.response.send_message(
                f"<:check:1485597845883981905> Переказано **{received}** {currency} користувачу {target_member.mention}.{tax_msg}", ephemeral=True
            )

class DepositTermView(discord.ui.View):
    def __init__(self, owner_id: int, eco: dict, terms: list):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.eco = eco
        
        for term in terms:
            btn = discord.ui.Button(label=term, style=discord.ButtonStyle.secondary)
            btn.callback = self.create_callback(term)
            self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("<:close:1485598320935174317> Це не твій вибір!", ephemeral=True)
            return False
        return True

    def create_callback(self, term: str):
        async def cb(interaction: discord.Interaction):
            await interaction.response.send_modal(ValueModal(self.owner_id, "deposit", self.eco, term))
        return cb

class HistoryPaginatorView(discord.ui.View):
    def __init__(self, owner_id: int, init_embed: discord.Embed, main_view: discord.ui.View, hist: list):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.init_embed = init_embed
        self.main_view = main_view
        self.hist = list(reversed(hist))
        self.page = 0
        self.per_page = 10
        self.filter_mode = "all"
        self._update_buttons()

    def _get_filtered_hist(self):
        if self.filter_mode == "all": return self.hist
        elif self.filter_mode == "+": return [h for h in self.hist if h["log"].startswith("🟢")]
        elif self.filter_mode == "-": return [h for h in self.hist if h["log"].startswith("🔴")]
        return self.hist

    def _update_buttons(self):
        filtered = self._get_filtered_hist()
        max_page = max(0, (len(filtered) - 1) // self.per_page)
        self.btn_prev.disabled = (self.page == 0)
        self.btn_next.disabled = (self.page >= max_page)
        self.btn_all.style = discord.ButtonStyle.primary if self.filter_mode == "all" else discord.ButtonStyle.secondary
        self.btn_pos.style = discord.ButtonStyle.success if self.filter_mode == "+" else discord.ButtonStyle.secondary
        self.btn_neg.style = discord.ButtonStyle.danger  if self.filter_mode == "-" else discord.ButtonStyle.secondary

    def _build_embed(self) -> discord.Embed:
        filtered = self._get_filtered_hist()
        max_page = max(0, (len(filtered) - 1) // self.per_page)
        embed = surface_embed("gameplay", f"{E_HISTORY} Історія транзакцій")
        if not filtered:
            embed.description = "Історія порожня."
        else:
            start = self.page * self.per_page
            lines = [h["log"] for h in filtered[start:start+self.per_page]]
            embed.description = "\n".join(lines)
        set_surface_footer(embed, "gameplay", f"Сторінка {self.page + 1}/{max_page + 1} • всього: {len(filtered)}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("<:close:1485598320935174317> Це не ваша історія!", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(E_BACK), style=discord.ButtonStyle.secondary, row=0)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        from commands.economy.economy import build_economy_embed
        embed = build_economy_embed(interaction.user, user_data, self.main_view.eco)
        await interaction.response.edit_message(embed=embed, view=self.main_view)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(E_BACK), style=discord.ButtonStyle.secondary, row=1)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(E_NEXT), style=discord.ButtonStyle.secondary, row=1)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="Всі", style=discord.ButtonStyle.primary, row=2)
    async def btn_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_mode = "all"
        self.page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="+Дохід", style=discord.ButtonStyle.secondary, row=2)
    async def btn_pos(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_mode = "+"
        self.page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="-Витрати", style=discord.ButtonStyle.secondary, row=2)
    async def btn_neg(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_mode = "-"
        self.page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

# ── Rob Modal (Пограбувати по ID прямо з /economy) ────────────────────────────

class RobModal(discord.ui.Modal, title="<:crimepass:1485614625025425529> Пограбування"):
    target_input = discord.ui.TextInput(
        label="Discord ID жертви",
        placeholder="123456789012345678",
        required=True,
        min_length=15,
        max_length=25
    )

    def __init__(self, owner_id: int, eco: dict, guild_id: int):
        super().__init__()
        self.owner_id = owner_id
        self.eco      = eco
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        import time as _t
        eco   = self.eco
        curr  = eco.get("currency_emoji", "<:coin:1485610808003133552>")

        raw = self.target_input.value.strip()
        if not raw.isdigit():
            return await interaction.response.send_message(f"{E_CROSS} Введіть числовий Discord ID.", ephemeral=True)

        from utils.eco_helpers import check_account_age
        if not await check_account_age(interaction, eco):
            return

        target_id = int(raw)
        if target_id == self.owner_id:
            return await interaction.response.send_message(f"{E_CROSS} Не можна грабувати себе.", ephemeral=True)

        target = interaction.guild.get_member(target_id)
        if not target or target.bot:
            return await interaction.response.send_message(f"{E_CROSS} Гравця з таким ID немає на сервері.", ephemeral=True)

        now      = int(_t.time())
        rob_cd   = eco.get("rob_cooldown", 3600)
        rob_data = await get_user(db, self.guild_id, self.owner_id)
        last_rob = rob_data.get("rob_last", 0)
        if last_rob and (now - last_rob) < rob_cd:
            remaining = rob_cd - (now - last_rob)
            m, s = divmod(remaining, 60)
            return await interaction.response.send_message(
                f"<:clock:1485618008784113796> Наступне пограбування через **{m}хв {s}с**.", ephemeral=True
            )

        victim_data   = await get_user(db, self.guild_id, target_id)
        if victim_data.get("shield_until", 0) > now:
            return await interaction.response.send_message(
                f"{E_CHECK} У **{target.display_name}** активний щит — пограбування неможливе.", ephemeral=True
            )

        victim_wallet = victim_data.get("wallet", 0)
        if victim_wallet < 10:
            return await interaction.response.send_message(
                f"{E_CROSS} У **{target.display_name}** немає грошей.", ephemeral=True
            )

        rob_chance  = eco.get("rob_chance", eco.get("rob_success_chance", 40))
        rob_pct_min = eco.get("rob_percent_min", 10)
        rob_pct_max = eco.get("rob_percent_max", 40)
        success     = random.random() * 100 < rob_chance

        stage = random.choice(ROB_STAGE_1)
        if success:
            pct    = random.randint(rob_pct_min, rob_pct_max)
            stolen = max(1, int(victim_wallet * pct / 100))
            
            victim_res = await db.users.find_one_and_update(
                {"guild_id": self.guild_id, "user_id": target_id, "wallet": {"$gte": stolen}},
                {
                    "$inc": {"wallet": -stolen},
                    "$push": {"eco_history": {"$each": [make_log(-stolen, f"Пограбований: {interaction.user.display_name}")], "$slice": -50}}
                }
            )
            
            if not victim_res:
                return await interaction.response.send_message(f"<:close:1485598320935174317> Жертва встигла заховати гроші...", ephemeral=True)

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, target_id)

            await db.users.update_one(
                {"guild_id": self.guild_id, "user_id": self.owner_id},
                {
                    "$inc": {"wallet": stolen},
                    "$set": {"rob_last": now},
                    "$push": {"eco_history": {"$each": [make_log(stolen, f"Пограбування: {target.display_name}")], "$slice": -50}}
                }
            )
            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, self.owner_id)

            await quest_hook(self.guild_id, self.owner_id, "economy.rob")
            embed = gameplay_result_embed(
                f"{E_ROBBERY} Успішне пограбування!",
                f"{stage['success']}\n\nЖертва: **{target.display_name}**\nВкрадено: **{stolen:,}** {curr} ({pct}%)",
                tone="success",
            )
        else:
            fine = max(0, int(rob_data.get("wallet", 0) * 0.15))
            
            if fine > 0:
                await db.users.update_one(
                    {"guild_id": self.guild_id, "user_id": self.owner_id},
                    {
                        "$inc": {"wallet": -fine},
                        "$set": {"rob_last": now},
                        "$push": {"eco_history": {"$each": [make_log(-fine, "Невдале пограбування: штраф")], "$slice": -50}}
                    }
                )
            else:
                await db.users.update_one(
                    {"guild_id": self.guild_id, "user_id": self.owner_id},
                    {"$set": {"rob_last": now}}
                )

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, self.owner_id)

            embed = gameplay_result_embed(
                f"{E_CROSS} Спіймали!",
                f"{stage['fail']}\n\nШтраф: **{fine:,}** {curr}",
                tone="danger",
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class MainEconomyView(discord.ui.View):
    def __init__(self, owner_id: int, init_embed: discord.Embed, eco: dict):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.init_embed = init_embed
        self.eco = eco

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("<:close:1485598320935174317> Це не твій гаманець!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Депозит", style=discord.ButtonStyle.secondary)
    async def deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        terms_str = self.eco.get("deposit_terms", "")
        if terms_str:
            terms = [t.strip() for t in terms_str.split(",") if t.strip()]
            if terms:
                view = DepositTermView(self.owner_id, self.eco, terms)
                
                await interaction.response.send_message("Оберіть термін депозиту (відсотки будуть нараховані після завершення):", view=view, ephemeral=True)
                return
                
        await interaction.response.send_modal(ValueModal(self.owner_id, "deposit", self.eco))

    @discord.ui.button(label="Зняти", style=discord.ButtonStyle.secondary)
    async def withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ValueModal(self.owner_id, "withdraw", self.eco))

    @discord.ui.button(label="Переказати", style=discord.ButtonStyle.secondary)
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ValueModal(self.owner_id, "transfer", self.eco))

    @discord.ui.button(label="Пограбувати", style=discord.ButtonStyle.danger, emoji=discord.PartialEmoji.from_str(E_ROBBERY))
    async def rob_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.eco.get("rob_enabled", True):
            return await interaction.response.send_message(f"{E_CROSS} Пограбування вимкнено на цьому сервері.", ephemeral=True)
        await interaction.response.send_modal(RobModal(self.owner_id, self.eco, interaction.guild.id))

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:inbox:1485599203815325836>"), label="Інвентар", style=discord.ButtonStyle.secondary)
    async def inventory_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from commands.economy.shop import build_inventory_embed_and_view
        eco       = self.eco
        guild_id  = interaction.guild.id
        embed, view = await build_inventory_embed_and_view(interaction.user, guild_id, eco, self)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_HISTORY), label="Історія транзакцій")
    async def history(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        hist = user_data.get("eco_history", [])
        
        view = HistoryPaginatorView(self.owner_id, self.init_embed, self, hist)
        await interaction.response.edit_message(embed=view._build_embed(), view=view)

class HistoryBackView(discord.ui.View):
    def __init__(self, owner_id: int, org_embed: discord.Embed, main_view: discord.ui.View):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.org_embed = org_embed
        self.main_view = main_view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("<:close:1485598320935174317> Це не ваша історія!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_BACK))
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        embed = build_economy_embed(interaction.user, user_data, self.main_view.eco)
        await interaction.response.edit_message(embed=embed, view=self.main_view)

def build_economy_embed(user: discord.Member, data: dict, eco: dict) -> discord.Embed:
    wallet = data.get("wallet", 0)
    bank = data.get("bank", 0)
    level = data.get("level", 1)
    
    bank_limit = eco.get("bank_base_limit", 10000) + (eco.get("bank_level_multiplier", 1000) * level)
    emoji = eco.get("currency_emoji", "<:coin:1485610808003133552>")


    total = wallet + bank
    embed = surface_embed("gameplay", f"Гаманець {user.display_name}", "Огляд готівки, банку і швидких дій по економіці.")
    add_section(
        embed,
        "Баланс",
        [
            compact_kv("Готівка", f"**{wallet:,}** {emoji}"),
            compact_kv("Банк", f"**{bank:,} / {bank_limit:,}** {emoji}"),
            compact_kv("Загалом", f"**{total:,}** {emoji}"),
        ],
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    set_surface_footer(embed, "gameplay", "Швидкі дії нижче: банк, переказ, пограбування, інвентар, історія.")
    return embed

class EconomyCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="economy", description="Відкрити свій гаманець та керувати коштами")
    async def economy(self, interaction: discord.Interaction):
        from modules.db import get_guild_settings
        settings = await get_guild_settings(db, interaction.guild.id)
        eco = settings.get("economy", {})
        if not eco.get("enabled", True):
            return await interaction.response.send_message("<:close:1485598320935174317> Економіка на цьому сервері вимкнена.", ephemeral=True)

        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        embed = build_economy_embed(interaction.user, user_data, eco)
        
        view = MainEconomyView(interaction.user.id, embed, eco)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(EconomyCommand(bot))
