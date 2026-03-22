from __future__ import annotations

import random
import time
import asyncio
from collections import defaultdict
import discord
from discord import app_commands
from discord.ext import commands

from modules.db import get_database
from repositories.user import get_user
from commands.administration.economy_setup import DEFAULT_ECO, get_eco
from commands.economy.quests import quest_hook
from utils.eco_helpers import make_log
from utils.ui_contract import gameplay_result_embed, set_surface_footer, surface_embed

db = get_database()

# defaultdict атомарно створює Lock при першому зверненні — без race condition
_USER_LOCKS: defaultdict[tuple, asyncio.Lock] = defaultdict(asyncio.Lock)

def _get_lock(guild_id: int, user_id: int) -> asyncio.Lock:
    return _USER_LOCKS[(guild_id, user_id)]

from config.constants import Emojis as _E
E_COIN     = _E.COIN.value
E_CROSS    = _E.CROSS.value
E_CHECK    = _E.CHECK.value
E_SLOTS    = _E.SLOTS.value
E_HELP     = _E.HELP.value
COLOR_WIN  = 0x57f287
COLOR_LOSE = 0xed4245
COLOR_BASE = 0x1a1a2e
COLOR_DRAW = 0xffa500


def _gameplay_tone_from_color(color: int) -> str:
    if color == COLOR_WIN:
        return "success"
    if color == COLOR_LOSE:
        return "danger"
    if color == COLOR_DRAW:
        return "warning"
    return "base"

async def check_economy(interaction: discord.Interaction) -> dict | None:
    from modules.db import get_guild_settings
    settings = await get_guild_settings(db, interaction.guild.id)
    eco = get_eco(settings)

    if not eco.get("enabled", True):
        await interaction.response.send_message("<:cutiex:1480246146076119132> Економіка вимкнена.", ephemeral=True)
        return None
    if not eco.get("gambling_enabled", False):
        await interaction.response.send_message(
            "🎰 Гемблінг вимкнено на цьому сервері. Адмін може увімкнути через `/economy_setup`.",
            ephemeral=True
        )
        return None

    # Перевірка кулдауну між ставками (анти-спам)
    cooldown = eco.get("gambling_cooldown", 0)
    if cooldown > 0:
        import time as _t
        from modules.db import get_user_data
        user_data = await get_user_data(db, interaction.guild.id, interaction.user.id)
        last_bet = user_data.get("gambling_last", 0)
        now = int(_t.time())
        if now - last_bet < cooldown:
            remaining = cooldown - (now - last_bet)
            from utils.eco_helpers import fmt_duration
            await interaction.response.send_message(
                f"<:Hourglass:1479950504321745026> Почекай ще **{fmt_duration(remaining)}** між ставками.", ephemeral=True
            )
            return None

    return eco

async def check_balance(interaction: discord.Interaction, user_data: dict, bet: int, eco: dict) -> bool:
    curr    = eco.get("currency_emoji", E_COIN)
    max_bet = eco.get("gambling_max_bet", 10000)
    daily_cap = eco.get("gambling_daily_cap", 0)

    if bet <= 0:
        await interaction.response.send_message(f"{E_CROSS} Ставка має бути більше 0.", ephemeral=True)
        return False
    if bet > max_bet:
        await interaction.response.send_message(
            f"{E_CROSS} Максимальна ставка: **{max_bet:,}** {curr}.", ephemeral=True
        )
        return False
    if user_data.get("wallet", 0) < bet:
        await interaction.response.send_message(
            f"{E_CROSS} Недостатньо монет у гаманці. Твій баланс: **{user_data.get('wallet', 0):,}** {curr}.",
            ephemeral=True
        )
        return False
    if daily_cap > 0:
        import time as _t
        today = _t.strftime("%Y-%m-%d")
        if user_data.get("gambling_cap_date", "") == today:
            earned_today = user_data.get("gambling_earned_today", 0)
            if earned_today >= daily_cap:
                await interaction.response.send_message(
                    f"{E_CROSS} Добовий ліміт виграшу: **{daily_cap:,}** {curr}. Спробуй завтра.", ephemeral=True
                )
                return False
    return True

async def atomic_bet(interaction: discord.Interaction, bet: int, eco: dict) -> bool:
    
    user_data = await get_user(db, interaction.guild.id, interaction.user.id)
    if not await check_balance(interaction, user_data, bet, eco):
        return False
        
    result = await db.users.find_one_and_update(
        {"guild_id": interaction.guild.id, "user_id": interaction.user.id, "wallet": {"$gte": bet}},
        {"$inc": {"wallet": -bet}}
    )
    if result:
        from modules.db import invalidate_user_data
        await invalidate_user_data(interaction.guild.id, interaction.user.id)
    if not result:
        curr = eco.get("currency_emoji", E_COIN)
        await interaction.response.send_message(
            f"{E_CROSS} Недостатньо монет у гаманці для ставки або виконується інша транзакція.",
            ephemeral=True
        )
        return False
    return True

async def finalize(guild_id: int, user_id: int, delta: int, desc: str, eco: dict = None):
    
    if delta > 0 and eco is not None:
        rtp   = eco.get("casino_rtp", 95)
        delta = int(delta * rtp / 100)

    import time as _t
    today = _t.strftime("%Y-%m-%d")
    inc = {"wallet": delta, "total_earned": max(0, delta)}
    if delta > 0:
        inc["week_earned"]  = delta
        inc["month_earned"] = delta
        inc["gambling_earned_today"] = delta
    upd = {
        "$inc": inc,
        "$push": {"eco_history": {"$each": [make_log(delta, desc)], "$slice": -50}}
    }
    if delta > 0:
        upd["$set"] = {"gambling_cap_date": today}
    await db.users.update_one({"guild_id": guild_id, "user_id": user_id}, upd)
    await quest_hook(guild_id, user_id, "gambling")

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────

SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "💎", "⭐", "7️⃣"]
SLOT_WEIGHTS  = [30, 25, 20, 15, 5, 4, 1]

SLOT_PAYOUTS = {
    ("7️⃣", "7️⃣", "7️⃣"): 10.0,
    ("💎", "💎", "💎"): 7.0,
    ("⭐", "⭐", "⭐"): 5.0,
    ("🍇", "🍇", "🍇"): 4.0,
    ("🍊", "🍊", "🍊"): 3.0,
    ("🍋", "🍋", "🍋"): 2.5,
    ("🍒", "🍒", "🍒"): 2.0,
}

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────

def card_value(rank: str) -> int:
    if rank in ("J", "Q", "K"): return 10
    if rank == "A": return 11
    return int(rank)

def hand_total(cards: list) -> int:
    total = sum(card_value(r) for r, _ in cards)
    aces  = sum(1 for r, _ in cards if r == "A")
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total

def fmt_hand(cards: list) -> str:
    return "  ".join(f"`{r}{s}`" for r, s in cards)

def is_blackjack(cards: list) -> bool:
    
    return len(cards) == 2 and hand_total(cards) == 21

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────

BJ_HELP_TEXT = (
    "**🃏 Правила Блекджеку**\n\n"
    "Мета — набрати більше очок ніж дилер, не перевищивши **21**.\n\n"
    "**Карти:**\n"
    "• `2–10` — номінал\n"
    "• `J Q K` — 10 очок\n"
    "• `A` — 11 або 1 (автоматично)\n\n"
    "**Дії:**\n"
    "• **Hit** — взяти ще карту\n"
    "• **Stand** — зупинитись, дилер добирає\n"
    "• **Double Down** — подвоїти ставку, взяти 1 карту і зупинитись\n"
    "• **Split** — якщо перші 2 карти однакові: розбити на 2 руки\n\n"
    "**Blackjack** (А + 10/J/Q/K) = виплата **1.5×** ставки <:firecracker:1479953348185555077>\n"
    "**Дилер** добирає до 17+."
)

class BlackjackView(discord.ui.View):
    def __init__(self, owner_id, bet, p_cards, d_cards, deck, eco, guild_id, user_data,
                 split_mode=False, split_hand_b=None, current_hand="a"):
        super().__init__(timeout=60)
        self.owner_id    = owner_id
        self.bet         = bet
        self.p_cards     = p_cards      
        self.d_cards     = d_cards
        self.deck        = deck
        self.eco         = eco
        self.guild_id    = guild_id
        self.user_data   = user_data
        self.split_mode  = split_mode
        self.split_hand_b = split_hand_b or []  
        self.current_hand = current_hand  
        self.finished    = False

        if split_mode:
            self.double_down.disabled = True
            self.split_btn.disabled   = True

        self._refresh_action_buttons()

    def _refresh_action_buttons(self):
        active = self.p_cards if self.current_hand == "a" else self.split_hand_b
        
        self.double_down.disabled = len(active) != 2 or self.split_mode
        
        if not self.split_mode and len(self.p_cards) == 2:
            self.split_btn.disabled = self.p_cards[0][0] != self.p_cards[1][0]
        else:
            self.split_btn.disabled = True

    @property
    def active_hand(self):
        return self.p_cards if self.current_hand == "a" else self.split_hand_b

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.owner_id:
            await i.response.send_message("<:cutiex:1480246146076119132> Це не твоя гра!", ephemeral=True)
            return False
        return True

    def build_embed(self, reveal_dealer: bool = True) -> discord.Embed:
        curr  = self.eco.get("currency_emoji", E_COIN)
        p_tot = hand_total(self.p_cards)
        d_tot = hand_total(self.d_cards)

        embed = surface_embed("gameplay", "🃏 Blackjack")

        if self.split_mode:
            marker_a = "▶ " if self.current_hand == "a" else ""
            marker_b = "▶ " if self.current_hand == "b" else ""
            b_tot = hand_total(self.split_hand_b) if self.split_hand_b else 0
            embed.add_field(
                name=f"{marker_a}Рука A ({p_tot})",
                value=fmt_hand(self.p_cards),
                inline=True
            )
            embed.add_field(
                name=f"{marker_b}Рука B ({b_tot})",
                value=fmt_hand(self.split_hand_b) if self.split_hand_b else "`?`",
                inline=True
            )
        else:
            embed.add_field(
                name=f"Твоя рука ({p_tot})",
                value=fmt_hand(self.p_cards),
                inline=False
            )

        if reveal_dealer:
            embed.add_field(name=f"Дилер ({d_tot})", value=fmt_hand(self.d_cards), inline=False)
        else:
            embed.add_field(
                name="Дилер (?)",
                value=f"`{self.d_cards[0][0]}{self.d_cards[0][1]}`  `🂠`",
                inline=False
            )
        set_surface_footer(embed, "gameplay", f"Ставка: {self.bet:,} {self.eco['currency_name']}")
        return embed

    async def _end(self, interaction: discord.Interaction, payout: int, msg: str, color: int):
        for child in self.children:
            child.disabled = True
        curr  = self.eco.get("currency_emoji", E_COIN)
        embed = surface_embed("gameplay", "🃏 Blackjack — Результат", tone=_gameplay_tone_from_color(color))
        embed.add_field(name=f"Твоя рука ({hand_total(self.p_cards)})", value=fmt_hand(self.p_cards), inline=False)
        embed.add_field(name=f"Дилер ({hand_total(self.d_cards)})",     value=fmt_hand(self.d_cards),  inline=False)
        
        net_profit = payout - self.bet if not self.split_mode else payout - (self.bet * 2) 
        embed.add_field(name="Підсумок", value=f"{msg} **{abs(net_profit):,}** {curr}", inline=False)
        
        await finalize(self.guild_id, self.owner_id, payout, f"Blackjack {'WIN' if net_profit > 0 else 'PUSH' if net_profit == 0 else 'LOSE'}", self.eco)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🃏 Hit", style=discord.ButtonStyle.primary, row=0)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        active = self.active_hand
        active.append(self.deck.pop())
        p_tot = hand_total(active)
        self._refresh_action_buttons()
        if p_tot > 21:
            if self.split_mode and self.current_hand == "a":
                
                self.current_hand = "b"
                self._refresh_action_buttons()
                await interaction.response.edit_message(embed=self.build_embed(reveal_dealer=False), view=self)
            else:
                await self._end(interaction, 0, "💥 Перебір! Програш:", COLOR_LOSE)
        elif p_tot == 21:
            await self._stand_logic(interaction)
        else:
            await interaction.response.edit_message(embed=self.build_embed(reveal_dealer=False), view=self)

    @discord.ui.button(label="✋ Stand", style=discord.ButtonStyle.secondary, row=0)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._stand_logic(interaction)

    async def _stand_logic(self, interaction: discord.Interaction):
        if self.split_mode and self.current_hand == "a":
            self.current_hand = "b"
            self._refresh_action_buttons()
            await interaction.response.edit_message(embed=self.build_embed(reveal_dealer=False), view=self)
            return

        while hand_total(self.d_cards) < 17:
            self.d_cards.append(self.deck.pop())

        p_tot = hand_total(self.p_cards)
        d_tot = hand_total(self.d_cards)

        if self.split_mode:
            b_tot = hand_total(self.split_hand_b)
            
            total_delta = 0  
            for hand_tot_val in [p_tot, b_tot]:
                if d_tot > 21 or hand_tot_val > d_tot:
                    total_delta += self.bet * 2
                elif hand_tot_val == d_tot:
                    total_delta += self.bet  
                else:
                    total_delta += 0

            for child in self.children:
                child.disabled = True
            curr = self.eco.get("currency_emoji", E_COIN)
            net_profit = total_delta - (self.bet * 2) 
            embed = surface_embed("gameplay", "🃏 Blackjack — Результат (Split)", tone="success" if net_profit > 0 else "danger" if net_profit < 0 else "warning")
            embed.add_field(name=f"Рука A ({p_tot})", value=fmt_hand(self.p_cards), inline=True)
            embed.add_field(name=f"Рука B ({b_tot})", value=fmt_hand(self.split_hand_b), inline=True)
            embed.add_field(name=f"Дилер ({d_tot})", value=fmt_hand(self.d_cards), inline=False)
            result_str = f"{'<:cutiecheckmark:1479120440734650389> +' if net_profit > 0 else ('🤝 ' if net_profit == 0 else '<:cutiex:1480246146076119132> -')}**{abs(net_profit):,}** {curr}"
            embed.add_field(name="Підсумок", value=result_str, inline=False)
            await finalize(self.guild_id, self.owner_id, total_delta, f"Blackjack Split {'WIN' if net_profit > 0 else 'LOSE'}", self.eco)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            if d_tot > 21 or p_tot > d_tot:
                await self._end(interaction, self.bet * 2, "<:cutiecheckmark:1479120440734650389> Виграш! +", COLOR_WIN)
            elif p_tot == d_tot:
                await self._end(interaction, self.bet, "🤝 Нічия.", COLOR_DRAW)
            else:
                await self._end(interaction, 0, "<:cutiex:1480246146076119132> Дилер переміг. -", COLOR_LOSE)

    @discord.ui.button(label="2× Double", style=discord.ButtonStyle.danger, row=0)
    async def double_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        if self.user_data.get("wallet", 0) < self.bet * 2:
            await interaction.response.send_message(
                f"{E_CROSS} Не вистачає монет для Double Down.", ephemeral=True
            )
            return
        
        result = await db.users.find_one_and_update(
            {"guild_id": self.guild_id, "user_id": self.owner_id, "wallet": {"$gte": self.bet}},
            {"$inc": {"wallet": -self.bet}}
        )
        if not result:
            await interaction.response.send_message(f"{E_CROSS} Недостатньо коштів для Double Down.", ephemeral=True)
            return

        from modules.db import invalidate_user_data
        await invalidate_user_data(interaction.guild.id, self.owner_id)

        self.bet *= 2
        self.p_cards.append(self.deck.pop())
        p_tot = hand_total(self.p_cards)
        if p_tot > 21:
            await self._end(interaction, 0, "💥 Перебір після Double! Програш:", COLOR_LOSE)
        else:
            await self._stand_logic(interaction)

    @discord.ui.button(label="✂️ Split", style=discord.ButtonStyle.secondary, row=0)
    async def split_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_data.get("wallet", 0) < self.bet:
            await interaction.response.send_message(
                f"{E_CROSS} Не вистачає монет для Split (потрібна додаткова ставка).", ephemeral=True
            )
            return
        await db.users.update_one(
            {"guild_id": self.guild_id, "user_id": self.owner_id},
            {"$inc": {"wallet": -self.bet}}
        )
        from modules.db import invalidate_user_data
        await invalidate_user_data(interaction.guild.id, self.owner_id)
        
        card_b = self.p_cards.pop()
        self.split_hand_b = [card_b, self.deck.pop()]
        self.p_cards.append(self.deck.pop())
        self.split_mode   = True
        self.current_hand = "a"
        self._refresh_action_buttons()
        await interaction.response.edit_message(embed=self.build_embed(reveal_dealer=False), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:reasonqiestion:1476209697919860777>"), style=discord.ButtonStyle.secondary, row=1)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(description=BJ_HELP_TEXT, color=COLOR_BASE)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────

RED_NUMS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}

ROULETTE_HELP_TEXT = (
    "**🎡 Правила Рулетки**\n\n"
    "Кулька зупиняється на числі **0–36**.\n\n"
    "**Типи ставок:**\n"
    "```\n"
    "red / black     → ×2   (колір)\n"
    "odd / even      → ×2   (парне/непарне)\n"
    "1-18 / 19-36   → ×2   (половини)\n"
    "1-12 / 13-24\n"
    "25-36           → ×3   (дюжини)\n"
    "0–36 (число)   → ×35  (пряме попадання)\n"
    "```\n"
    "<:warn:1477376152191373504> Число **0** — програш для всіх ставок крім прямого `0`."
)

def resolve_roulette_bet(bet_type: str, result_num: int):
    
    bt = bet_type.strip().lower()
    is_red   = result_num in RED_NUMS
    is_black = result_num > 0 and result_num not in RED_NUMS

    if bt == "red":
        return (is_red, 2)
    elif bt == "black":
        return (is_black, 2)
    elif bt == "odd":
        return (result_num > 0 and result_num % 2 == 1, 2)
    elif bt == "even":
        return (result_num > 0 and result_num % 2 == 0, 2)
    elif bt in ("1-18",):
        return (1 <= result_num <= 18, 2)
    elif bt in ("19-36",):
        return (19 <= result_num <= 36, 2)
    elif bt in ("1-12",):
        return (1 <= result_num <= 12, 3)
    elif bt in ("13-24",):
        return (13 <= result_num <= 24, 3)
    elif bt in ("25-36",):
        return (25 <= result_num <= 36, 3)
    elif bt.isdigit() and 0 <= int(bt) <= 36:
        return (int(bt) == result_num, 35)
    return None

class RouletteView(discord.ui.View):
    
    def __init__(self, owner_id: int, bet: int, eco: dict, guild_id: int, user_data: dict):
        super().__init__(timeout=60)
        self.owner_id  = owner_id
        self.bet       = bet
        self.eco       = eco
        self.guild_id  = guild_id
        self.user_data = user_data

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.owner_id:
            await i.response.send_message("<:cutiex:1480246146076119132> Це не твоя гра!", ephemeral=True)
            return False
        return True

    async def _spin(self, interaction: discord.Interaction, bet_type: str):
        for child in self.children:
            child.disabled = True

        result_num   = random.randint(0, 36)
        res = resolve_roulette_bet(bet_type, result_num)
        if res is None:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Помилка типу ставки.", ephemeral=True)
            return

        won, mult = res
        payout = self.bet * mult if won else 0
        net_profit = payout - self.bet
        curr  = self.eco.get("currency_emoji", E_COIN)

        # ── Анімація ──────────────────────────────────────────────────────────
        await interaction.response.defer()

        def _spin_frame(step: int) -> discord.Embed:
            nums = [random.randint(0, 36) for _ in range(5)]
            slots = " | ".join(f"**{n}**" for n in nums)
            e = surface_embed("gameplay", "🎡 Рулетка крутиться...")
            e.add_field(name=f"{'🔄' * step} Кулька летить...", value=f"[ {slots} ]", inline=False)
            set_surface_footer(e, "gameplay", f"Ставка: {self.bet:,} {self.eco['currency_name']}")
            return e

        for step in range(1, 4):
            await interaction.edit_original_response(embed=_spin_frame(step), view=self)
            await asyncio.sleep(0.85)

        # ── Фінал ─────────────────────────────────────────────────────────────
        await finalize(self.guild_id, self.owner_id, payout, f"Roulette {'WIN' if won else 'LOSE'}", self.eco)

        result_color = "🔴" if result_num in RED_NUMS else ("⚫ Zero" if result_num == 0 else "⚫")
        embed = surface_embed("gameplay", "🎡 Рулетка зупинилась!", tone="success" if won else "danger")
        embed.add_field(name="Випало", value=f"**{result_num}** {result_color}", inline=True)
        embed.add_field(name="Ставка", value=f"`{bet_type}`  ×{mult}", inline=True)
        embed.add_field(
            name="Результат",
            value=f"{'<:cutiecheckmark:1479120440734650389> **Виграш!** +' if won else '<:cutiex:1480246146076119132> **Програш.** -'}**{abs(net_profit):,}** {curr}",
            inline=False
        )
        await interaction.edit_original_response(embed=embed, view=self)

    # ── Кнопки кольорів ────────────────────────────────────────────────────────
    @discord.ui.button(label="🔴 Red", style=discord.ButtonStyle.danger, row=0)
    async def red(self, i, b): await self._spin(i, "red")

    @discord.ui.button(label="⚫ Black", style=discord.ButtonStyle.secondary, row=0)
    async def black(self, i, b): await self._spin(i, "black")

    @discord.ui.button(label="Odd", style=discord.ButtonStyle.secondary, row=0)
    async def odd(self, i, b): await self._spin(i, "odd")

    @discord.ui.button(label="Even", style=discord.ButtonStyle.secondary, row=0)
    async def even(self, i, b): await self._spin(i, "even")

    # ── Кнопки половин ─────────────────────────────────────────────────────────
    @discord.ui.button(label="1–18", style=discord.ButtonStyle.secondary, row=1)
    async def half_low(self, i, b): await self._spin(i, "1-18")

    @discord.ui.button(label="19–36", style=discord.ButtonStyle.secondary, row=1)
    async def half_high(self, i, b): await self._spin(i, "19-36")

    # ── Кнопки дюжин ───────────────────────────────────────────────────────────
    @discord.ui.button(label="1–12", style=discord.ButtonStyle.secondary, row=2)
    async def dozen1(self, i, b): await self._spin(i, "1-12")

    @discord.ui.button(label="13–24", style=discord.ButtonStyle.secondary, row=2)
    async def dozen2(self, i, b): await self._spin(i, "13-24")

    @discord.ui.button(label="25–36", style=discord.ButtonStyle.secondary, row=2)
    async def dozen3(self, i, b): await self._spin(i, "25-36")

    # ── Help ───────────────────────────────────────────────────────────────────
    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:reasonqiestion:1476209697919860777>"), style=discord.ButtonStyle.secondary, row=3)
    async def help_btn(self, i: discord.Interaction, b):
        embed = discord.Embed(description=ROULETTE_HELP_TEXT, color=COLOR_BASE)
        await i.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────

class HighLowView(discord.ui.View):
    def __init__(self, owner_id, bet, first_num, eco, guild_id, user_data):
        super().__init__(timeout=30)
        self.owner_id  = owner_id
        self.bet       = bet
        self.first_num = first_num
        self.eco       = eco
        self.guild_id  = guild_id
        self.user_data = user_data

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.owner_id:
            await i.response.send_message("<:cutiex:1480246146076119132> Це не твоя гра!", ephemeral=True)
            return False
        return True

    async def _resolve(self, interaction: discord.Interaction, guess_higher: bool):
        for child in self.children: child.disabled = True
        second = random.randint(1, 100)
        curr = self.eco.get("currency_emoji", E_COIN)

        if second == self.first_num:
            won = None
        else:
            won = (second > self.first_num) == guess_higher

        if won is None:
            delta  = self.bet
            result = f"🤝 Нічия! Числа однакові ({second}). Ставку повернено."
            color  = COLOR_DRAW
        elif won:
            delta  = self.bet * 2
            result = f"<:cutiecheckmark:1479120440734650389> Правильно! Були **{self.first_num}** → **{second}**. +**{self.bet:,}** {curr}"
            color  = COLOR_WIN
        else:
            delta  = 0
            result = f"<:cutiex:1480246146076119132> Неправильно! Були **{self.first_num}** → **{second}**. -**{self.bet:,}** {curr}"
            color  = COLOR_LOSE

        await finalize(self.guild_id, self.owner_id, delta, f"HighLow {'WIN' if won else ('DRAW' if won is None else 'LOSE')}", self.eco)

        embed = gameplay_result_embed("📊 High or Low — Результат", result, tone=_gameplay_tone_from_color(color))
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="📈 Вище",  style=discord.ButtonStyle.success)
    async def higher(self, i, b): await self._resolve(i, True)

    @discord.ui.button(label="📉 Нижче", style=discord.ButtonStyle.danger)
    async def lower(self, i, b): await self._resolve(i, False)

    async def on_timeout(self):
        for child in self.children: child.disabled = True

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────

class GamblingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /slots ────────────────────────────────────────────────────────────────

    @app_commands.command(name="slots", description="Зіграти в слот-машину")
    @app_commands.describe(ставка="Скільки монет поставити")
    async def slots(self, interaction: discord.Interaction, ставка: int):
        eco = await check_economy(interaction)
        if not eco: return
        
        if not await atomic_bet(interaction, ставка, eco): return

        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        curr = eco.get("currency_emoji", E_COIN)
        reels = random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
        combo = tuple(reels)

        spin_embed = surface_embed("gameplay", f"{E_SLOTS} Slot Machine", "Барабани вже крутяться.")
        spin_embed.add_field(name="Барабани", value="**[ ❓ | ❓ | ❓ ]**", inline=False)
        set_surface_footer(spin_embed, "gameplay", f"Ставка: {ставка:,} {eco['currency_name']}")
        await interaction.response.send_message(embed=spin_embed, ephemeral=True)
        msg = await interaction.original_response()

        await asyncio.sleep(1)
        spin_embed.set_field_at(0, name="Барабани", value=f"**[ {reels[0]} | ❓ | ❓ ]**", inline=False)
        await msg.edit(embed=spin_embed)

        await asyncio.sleep(1)
        spin_embed.set_field_at(0, name="Барабани", value=f"**[ {reels[0]} | {reels[1]} | ❓ ]**", inline=False)
        await msg.edit(embed=spin_embed)

        await asyncio.sleep(1)
        payout_mult = SLOT_PAYOUTS.get(combo, 0)
        if payout_mult:
            winnings = int(ставка * payout_mult)
            delta    = winnings - ставка
            color    = COLOR_WIN
            result   = f"<:firecracker:1479953348185555077> Виграш! **+{delta:,}** {curr}  *(×{payout_mult})*"
        else:
            delta  = -ставка
            color  = COLOR_LOSE
            result = f"😞 Не пощастило. **{ставка:,}** {curr} списано."

        await finalize(interaction.guild.id, interaction.user.id, winnings if payout_mult else 0, f"Slots {'WIN' if payout_mult else 'LOSE'}", eco)

        user_data_new = await get_user(db, interaction.guild.id, interaction.user.id)
        new_wallet = user_data_new.get("wallet", 0)
        final_embed = surface_embed("gameplay", f"{E_SLOTS} Slot Machine", tone=_gameplay_tone_from_color(color))
        final_embed.add_field(name="Барабани", value=f"**[ {reels[0]} | {reels[1]} | {reels[2]} ]**", inline=False)
        final_embed.add_field(name="Результат", value=result, inline=False)
        set_surface_footer(final_embed, "gameplay", f"Гаманець: {new_wallet:,} {eco['currency_name']}")
        await msg.edit(embed=final_embed)

    # ── /coinflip ─────────────────────────────────────────────────────────────

    @app_commands.command(name="coinflip", description="Орел або решка")
    @app_commands.describe(ставка="Скільки поставити", вибір="heads (Орел) або tails (Решка)")
    @app_commands.choices(вибір=[
        app_commands.Choice(name="🦅 Орел", value="heads"),
        app_commands.Choice(name="🪙 Решка", value="tails"),
    ])
    async def coinflip(self, interaction: discord.Interaction, ставка: int, вибір: str):
        eco = await check_economy(interaction)
        if not eco: return
        
        if not await atomic_bet(interaction, ставка, eco): return

        curr = eco.get("currency_emoji", E_COIN)
        result = random.choice(["heads", "tails"])
        won = result == вибір

        result_name = "🦅 Орел" if result == "heads" else "🪙 Решка"
        chosen_name = "🦅 Орел" if вибір == "heads" else "🪙 Решка"

        delta = ставка * 2 if won else 0
        await finalize(interaction.guild.id, interaction.user.id, delta, f"Coinflip {'WIN' if won else 'LOSE'}", eco)

        embed = surface_embed("gameplay", "🪙 Монетка у повітрі...", tone="success" if won else "danger")
        embed.add_field(name="Випало",     value=result_name, inline=True)
        embed.add_field(name="Твій вибір", value=chosen_name, inline=True)
        embed.add_field(
            name="Результат",
            value=f"{'<:cutiecheckmark:1479120440734650389> **Виграш!** +' if won else '<:cutiex:1480246146076119132> **Програш.** -'}**{ставка:,}** {curr}",
            inline=False
        )
        set_surface_footer(embed, "gameplay", f"Ставка: {ставка:,} {eco['currency_name']}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /highlow ──────────────────────────────────────────────────────────────

    @app_commands.command(name="highlow", description="Вгадай: наступне число вище чи нижче?")
    @app_commands.describe(ставка="Скільки поставити")
    async def highlow(self, interaction: discord.Interaction, ставка: int):
        eco = await check_economy(interaction)
        if not eco: return
        
        if not await atomic_bet(interaction, ставка, eco): return
        
        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        curr = eco.get("currency_emoji", E_COIN)
        first = random.randint(1, 100)

        embed = surface_embed(
            "gameplay",
            "📊 High or Low",
            f"Поточне число: **{first}**\n\nНаступне число буде *вище* чи *нижче*?",
        )
        set_surface_footer(embed, "gameplay", f"Ставка: {ставка:,} {eco['currency_name']}")

        view = HighLowView(interaction.user.id, ставка, first, eco, interaction.guild.id, user_data)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /blackjack ────────────────────────────────────────────────────────────

    @app_commands.command(name="blackjack", description="Зіграти в Блекджек проти дилера")
    @app_commands.describe(ставка="Скільки поставити")
    async def blackjack(self, interaction: discord.Interaction, ставка: int):
        eco = await check_economy(interaction)
        if not eco: return
        
        if not await atomic_bet(interaction, ставка, eco): return
        
        user_data = await get_user(db, interaction.guild.id, interaction.user.id)

        deck    = self._make_deck()
        p_cards = [deck.pop(), deck.pop()]
        d_cards = [deck.pop(), deck.pop()]

        if is_blackjack(p_cards):
            curr = eco.get("currency_emoji", E_COIN)
            if is_blackjack(d_cards):
                
                await db.users.update_one(
                    {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                    {"$inc": {"wallet": ставка}}
                )
                embed = gameplay_result_embed("🃏 Blackjack — Нічия!", f"Обидва мають Blackjack. Ставку **{ставка:,}** {curr} повернено.", tone="warning")
                embed.add_field(name=f"Твоя рука ({hand_total(p_cards)})", value=fmt_hand(p_cards), inline=True)
                embed.add_field(name=f"Дилер ({hand_total(d_cards)})", value=fmt_hand(d_cards), inline=True)
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                
                win_amount = int(ставка * 1.5)
                await db.users.update_one(
                    {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                    {"$inc": {"wallet": ставка + win_amount, "total_earned": win_amount, "week_earned": win_amount, "month_earned": win_amount}},
                )
                embed = gameplay_result_embed("🃏 BLACKJACK! <:firecracker:1479953348185555077>", f"Натуральний Blackjack! Виплата **×1.5** = **+{win_amount:,}** {curr}", tone="success")
                embed.add_field(name=f"Твоя рука ({hand_total(p_cards)})", value=fmt_hand(p_cards), inline=True)
                embed.add_field(name=f"Дилер ({hand_total(d_cards)})", value=fmt_hand(d_cards), inline=True)
                return await interaction.response.send_message(embed=embed, ephemeral=True)

        view  = BlackjackView(interaction.user.id, ставка, p_cards, d_cards, deck, eco, interaction.guild.id, user_data)
        embed = view.build_embed(reveal_dealer=False)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /roulette ─────────────────────────────────────────────────────────────

    @app_commands.command(name="roulette", description="Рулетка — обери тип ставки кнопками")
    @app_commands.describe(ставка="Скільки поставити")
    async def roulette(self, interaction: discord.Interaction, ставка: int):
        eco = await check_economy(interaction)
        if not eco: return
        
        if not await atomic_bet(interaction, ставка, eco): return

        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        curr = eco.get("currency_emoji", E_COIN)
        embed = surface_embed(
            "gameplay",
            "🎡 Рулетка",
            f"Ставка: **{ставка:,}** {curr}\n\nОбери тип ставки кнопками нижче:",
        )
        set_surface_footer(embed, "gameplay", "🔴/⚫ ×2  •  Odd/Even ×2  •  1-18/19-36 ×2  •  Дюжини ×3  •  Число ×35")
        view = RouletteView(interaction.user.id, ставка, eco, interaction.guild.id, user_data)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @staticmethod
    def _make_deck() -> list:
        suits  = ["♠️", "♥️", "♦️", "♣️"]
        ranks  = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        deck   = [(r, s) for s in suits for r in ranks]
        random.shuffle(deck)
        return deck

async def setup(bot):
    await bot.add_cog(GamblingCog(bot))
