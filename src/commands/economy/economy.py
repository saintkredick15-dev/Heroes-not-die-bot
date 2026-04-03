import discord
from discord import app_commands
from discord.ext import commands
import time
import random
import math

from commands.administration.economy_setup_shared import get_eco, normalize_currency_emoji
from config.constants import Emojis as _E
from modules.db import get_database
from repositories.user import get_user
from commands.economy.quests import quest_hook
from services.metrics import inc_global_metrics
from utils.eco_helpers import make_log
from utils.ui_contract import add_section, compact_kv, gameplay_result_embed, set_surface_footer, surface_embed

db = get_database()

E_HISTORY = _E.HISTORY.value
E_ROBBERY = _E.ROBBERY.value
E_BACK    = _E.BACK.value
E_NEXT    = _E.NEXT.value
E_INBOX   = _E.INBOX.value
E_CHECK   = _E.CHECK.value
E_CROSS   = _E.CROSS.value
E_BANK    = _E.BANK.value
E_WALLET  = _E.WALLET.value
E_TRANSFER = _E.CARD_TRANSFER.value
E_PLUS    = _E.PLUS.value
E_MINUS   = _E.MINUS.value
E_CLOCK   = _E.CLOCK.value


def _currency_emoji(eco: dict) -> str:
    return normalize_currency_emoji(eco.get("currency_emoji") or _E.COIN.value)

class ValueModal(discord.ui.Modal):
    def __init__(self, owner_id: int, action: str, eco: dict, term: str = None, source_channel_id: int | None = None, source_message_id: int | None = None):
        titles = {
            "deposit": "Депозит у банк" + (f" ({term})" if term else ""),
            "withdraw": "Зняття з банку",
            "transfer": "Переказ коштів",
        }
        super().__init__(title=titles.get(action, "Операція"))
        self.owner_id = owner_id
        self.action = action
        self.eco = eco
        self.term = term
        self.source_channel_id = source_channel_id
        self.source_message_id = source_message_id

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

    async def _refresh_main_message(self, interaction: discord.Interaction):
        if not self.source_channel_id or not self.source_message_id:
            return
        try:
            channel = interaction.guild.get_channel(self.source_channel_id) or interaction.client.get_channel(self.source_channel_id)
            if channel is None:
                channel = await interaction.client.fetch_channel(self.source_channel_id)
            message = await channel.fetch_message(self.source_message_id)
            user_data = await get_user(db, interaction.guild.id, interaction.user.id)
            embed = build_economy_embed(interaction.user, user_data, self.eco)
            view = MainEconomyView(self.owner_id, embed, self.eco)
            await message.edit(embed=embed, view=view)
        except Exception:
            pass

    async def on_submit(self, interaction: discord.Interaction):
        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        wallet = user_data.get("wallet", 0)
        bank = user_data.get("bank", 0)
        level = user_data.get("level", 1)
        bank_limit = self.eco.get("bank_base_limit", 10000) + (self.eco.get("bank_level_multiplier", 1000) * level)
        currency = _currency_emoji(self.eco)

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
                return await interaction.response.send_message(f"{E_CROSS} Будь ласка, введіть число або 'all'.", ephemeral=True)

        if amount <= 0:
            return await interaction.response.send_message(f"{E_CROSS} Сума має бути більшою за нуль.", ephemeral=True)

        log_item = None
        if self.action == "deposit":
            if bank + amount > bank_limit:
                max_dep = bank_limit - bank
                if max_dep <= 0:
                    return await interaction.response.send_message(f"{E_CROSS} Ваш банк переповнений!", ephemeral=True)
                return await interaction.response.send_message(f"{E_CROSS} Ви не можете покласти стільки. Доступне місце: **{max_dep}** {currency}", ephemeral=True)
            
            desc = f"Депозит у банк" + (f" (Термін: {self.term})" if self.term else "")
            log_item = make_log(-amount, desc)
            
            result = await db.users.find_one_and_update(
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id, "wallet": {"$gte": amount}},
                {"$inc": {"wallet": -amount, "bank": amount}, "$push": {"eco_history": {"$each": [log_item], "$slice": -50}}}
            )
            
            if not result:
                return await interaction.response.send_message(f"{E_CROSS} Недостатньо коштів у гаманці. У вас: **{wallet}** {currency}", ephemeral=True)

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, interaction.user.id)

            await quest_hook(interaction.guild.id, interaction.user.id, "economy.deposit")
            await self._refresh_main_message(interaction)
            await interaction.response.send_message(f"{E_CHECK} Ви успішно поклали **{amount}** {currency} у банк" + (f" на термін **{self.term}**" if self.term else "") + ".", ephemeral=True)

        elif self.action == "withdraw":
            log_item = make_log(amount, "Зняття з банку")
            
            result = await db.users.find_one_and_update(
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id, "bank": {"$gte": amount}},
                {"$inc": {"wallet": amount, "bank": -amount}, "$push": {"eco_history": {"$each": [log_item], "$slice": -50}}}
            )
            
            if not result:
                return await interaction.response.send_message(f"{E_CROSS} Недостатньо коштів у банку. У вас: **{bank}** {currency}", ephemeral=True)

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, interaction.user.id)

            await self._refresh_main_message(interaction)
            await interaction.response.send_message(f"{E_CHECK} Ви успішно зняли **{amount}** {currency} з банку.", ephemeral=True)

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
                return await interaction.response.send_message(f"{E_CROSS} ID отримувача має складатися з цифр.", ephemeral=True)
            target_user_id = int(raw_id)

            if target_user_id == interaction.user.id:
                return await interaction.response.send_message(f"{E_CROSS} Не можна переказати кошти самому собі.", ephemeral=True)

            target_member = interaction.guild.get_member(target_user_id)
            if not target_member or target_member.bot:
                return await interaction.response.send_message(f"{E_CROSS} Неможливо знайти такого користувача.", ephemeral=True)

            tax_amount = math.ceil(amount * tax_pct / 100) if tax_pct > 0 else 0
            received   = amount - tax_amount
            if received <= 0:
                return await interaction.response.send_message(
                    f"{E_CROSS} Після податку переказ не залишає валідної суми для отримувача.",
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
                        f"{E_CROSS} Добовий ліміт переказів: `{day_lim:,}` {currency}. Залишилось: `{remaining:,}`", ephemeral=True
                    )
                return await interaction.response.send_message(f"{E_CROSS} Недостатньо коштів. У вас: **{wallet}** {currency}", ephemeral=True)

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
            if tax_amount > 0:
                await inc_global_metrics({
                    "economy_tax_collected": tax_amount,
                    "economy_total_spent": tax_amount,
                })
            await invalidate_user_data(interaction.guild.id, target_user_id)
            tax_msg = f" (податок: **{tax_amount}** {currency})" if tax_amount else ""
            await self._refresh_main_message(interaction)
            await interaction.response.send_message(
                f"{E_CHECK} Переказано **{received}** {currency} користувачу {target_member.mention}.{tax_msg}", ephemeral=True
            )

class DepositTermSelect(discord.ui.Select):
    def __init__(self, owner_id: int, eco: dict, terms: list[str], source_channel_id: int | None = None, source_message_id: int | None = None):
        self.owner_id = owner_id
        self.eco = eco
        self.source_channel_id = source_channel_id
        self.source_message_id = source_message_id
        options = [discord.SelectOption(label=term, value=term) for term in terms[:25]]
        super().__init__(placeholder="Оберіть термін депозиту...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            ValueModal(
                self.owner_id,
                "deposit",
                self.eco,
                self.values[0],
                source_channel_id=self.source_channel_id,
                source_message_id=self.source_message_id,
            )
        )


class DepositTermView(discord.ui.View):
    def __init__(self, owner_id: int, eco: dict, terms: list, source_channel_id: int | None = None, source_message_id: int | None = None):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.eco = eco
        self.add_item(DepositTermSelect(owner_id, eco, terms, source_channel_id, source_message_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(f"{E_CROSS} Це не твій вибір!", ephemeral=True)
            return False
        return True

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
        elif self.filter_mode == "+": return [h for h in self.hist if h["log"].startswith(E_PLUS)]
        elif self.filter_mode == "-": return [h for h in self.hist if h["log"].startswith(E_MINUS)]
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
            await interaction.response.send_message(f"{E_CROSS} Це не ваша історія!", ephemeral=True)
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

class MainEconomyView(discord.ui.View):
    def __init__(self, owner_id: int, init_embed: discord.Embed, eco: dict):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.init_embed = init_embed
        self.eco = eco

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(f"{E_CROSS} Це не твій гаманець!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Депозит", style=discord.ButtonStyle.secondary)
    async def deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        terms_raw = self.eco.get("deposit_terms", "")
        if isinstance(terms_raw, list):
            terms = [str(term).strip() for term in terms_raw if str(term).strip()]
        else:
            terms = [t.strip() for t in str(terms_raw).split(",") if t.strip()]
        if terms:
            embed = surface_embed("admin", f"{E_BANK} Депозит", "Оберіть термін депозиту.")
            view = DepositTermView(self.owner_id, self.eco, terms, interaction.channel.id, interaction.message.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        await interaction.response.send_modal(ValueModal(self.owner_id, "deposit", self.eco, source_channel_id=interaction.channel.id, source_message_id=interaction.message.id))

    @discord.ui.button(label="Зняти", style=discord.ButtonStyle.secondary)
    async def withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ValueModal(self.owner_id, "withdraw", self.eco, source_channel_id=interaction.channel.id, source_message_id=interaction.message.id))

    @discord.ui.button(label="Переказати", style=discord.ButtonStyle.secondary)
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ValueModal(self.owner_id, "transfer", self.eco, source_channel_id=interaction.channel.id, source_message_id=interaction.message.id))

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(E_INBOX), label="Інвентар", style=discord.ButtonStyle.secondary)
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
            await interaction.response.send_message(f"{E_CROSS} Це не ваша історія!", ephemeral=True)
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
    emoji = _currency_emoji(eco)


    total = wallet + bank
    embed = surface_embed("admin", f"Гаманець {user.display_name}", "Баланс, банк і основні дії.")
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
    return embed

class EconomyCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="wallet", description="Відкрити свій гаманець і керувати коштами")
    async def wallet(self, interaction: discord.Interaction):
        from modules.db import get_guild_settings
        settings = await get_guild_settings(db, interaction.guild.id)
        eco = get_eco(settings)
        if not eco.get("enabled", True):
            return await interaction.response.send_message(f"{E_CROSS} Економіка на цьому сервері вимкнена.", ephemeral=True)

        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        embed = build_economy_embed(interaction.user, user_data, eco)
        
        view = MainEconomyView(interaction.user.id, embed, eco)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(EconomyCommand(bot))
