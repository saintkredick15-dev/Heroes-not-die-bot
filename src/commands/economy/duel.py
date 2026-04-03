"""
/duel @user <ставка> — Камінь Ножиці Папір до 3 перемог.
- публічний embed з countdown що оновлюється щосекунди
- ephemeral вибір ×кожен гравець (редагується/закривається після раунду)
- чорний дизайн embed
- після раунду - summary, потім 3с countdown до наступного
"""
from __future__ import annotations

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import time
import random

from config.constants import Emojis as _E
from modules.db import get_database
from repositories.user import get_user
from commands.administration.economy_setup_shared import get_eco, normalize_currency_emoji
from commands.economy.quests import quest_hook
from services.metrics import inc_global_metric
from utils.eco_helpers import make_log
from utils.ui_contract import gameplay_result_embed, set_surface_footer, surface_embed

db = get_database()
add_history = make_log

E_COIN   = _E.COIN.value
E_CHECK  = "<:check:1485597845883981905>"
E_CROSS  = "<:close:1485598320935174317>"

COLOR_BASE = 0x1a1a2e

ROCK     = "🪨"
PAPER    = "📄"
SCISSORS = "✂️"

RPS_NAMES  = {ROCK: "Камінь", PAPER: "Папір", SCISSORS: "Ножиці"}
BEATS      = {ROCK: SCISSORS, SCISSORS: PAPER, PAPER: ROCK}

# ── Стан раунду ──────────────────────────────────────────────────────────────

class RoundState:
    def __init__(self, ch_id: int, tg_id: int):
        self.choices: dict[int, str] = {}
        self.ch_id = ch_id
        self.tg_id = tg_id
        self.event  = asyncio.Event()

    def record(self, user_id: int, emoji: str):
        self.choices[user_id] = emoji
        if self.both_chose():
            self.event.set()

    def both_chose(self) -> bool:
        return self.ch_id in self.choices and self.tg_id in self.choices

    def resolve(self) -> tuple[int | None, str, str]:
        ch_e = self.choices.get(self.ch_id) or random.choice([ROCK, SCISSORS, PAPER])
        tg_e = self.choices.get(self.tg_id) or random.choice([ROCK, SCISSORS, PAPER])
        self.choices.setdefault(self.ch_id, ch_e)
        self.choices.setdefault(self.tg_id, tg_e)
        if ch_e == tg_e:
            return None, ch_e, tg_e
        if BEATS[ch_e] == tg_e:
            return self.ch_id, ch_e, tg_e
        return self.tg_id, ch_e, tg_e

# ── Ephemeral View для вибору ходу ────────────────────────────────────────────

class MoveView(discord.ui.View):
    def __init__(self, player_id: int, rs: RoundState):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.rs        = rs
        self.done      = False
        self._resp: discord.Interaction | None = None

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.player_id:
            await i.response.send_message("Це не твій хід!", ephemeral=True)
            return False
        if self.done:
            await i.response.send_message("Ти вже обрав!", ephemeral=True)
            return False
        return True

    async def _pick(self, i: discord.Interaction, emoji: str):
        self.done = True
        for c in self.children:
            c.disabled = True
        self.rs.record(i.user.id, emoji)
        self._resp = i
        await i.response.edit_message(
            embed=gameplay_result_embed("Хід зафіксовано", f"Ти обрав **{emoji}**\nЧекаємо на суперника...", tone="warning"),
            view=self
        )

    async def close_after_round(self, ch_e: str, tg_e: str, winner_id: int | None):
        """Редагує ephemeral повідомлення після завершення раунду."""
        if not self._resp:
            return
        my_emoji  = self.rs.choices.get(self.player_id, "?")
        opp_emoji = tg_e if self.player_id == self.rs.ch_id else ch_e
        if winner_id is None:
            res = "Нічия!"
        elif winner_id == self.player_id:
            res = "Ти виграв цей раунд!"
        else:
            res = "Ти програв цей раунд."
        try:
            await self._resp.edit_original_response(
                embed=gameplay_result_embed(
                    "Результат раунду",
                    f"{my_emoji} vs {opp_emoji}\n**{res}**",
                    tone="success" if winner_id == self.player_id else "warning" if winner_id is None else "danger",
                ),
                view=None
            )
        except Exception:
            pass

    @discord.ui.button(emoji=ROCK, style=discord.ButtonStyle.secondary)
    async def rock(self, i, b): await self._pick(i, ROCK)

    @discord.ui.button(emoji=SCISSORS, style=discord.ButtonStyle.secondary)
    async def scissors(self, i, b): await self._pick(i, SCISSORS)

    @discord.ui.button(emoji=PAPER, style=discord.ButtonStyle.secondary)
    async def paper(self, i, b): await self._pick(i, PAPER)

# ── Кнопка "Зробити хід" ─────────────────────────────────────────────────────

class RoundButton(discord.ui.View):
    def __init__(self, ch: discord.Member, tg: discord.Member, rs: RoundState):
        super().__init__(timeout=None)
        self.ch      = ch
        self.tg      = tg
        self.rs      = rs
        self.clicked: dict[int, MoveView] = {}

    @discord.ui.button(label="Зробити хід", style=discord.ButtonStyle.secondary)
    async def move(self, i: discord.Interaction, _):
        if i.user.id not in (self.ch.id, self.tg.id):
            await i.response.send_message("Ти не учасник!", ephemeral=True)
            return
        if i.user.id in self.clicked:
            await i.response.send_message("Ти вже натиснув, чекай суперника.", ephemeral=True)
            return
        mv = MoveView(i.user.id, self.rs)
        self.clicked[i.user.id] = mv
        await i.response.send_message(
            embed=surface_embed("gameplay", "Твій хід", "Обери хід нижче. Це видно тільки тобі."),
            view=mv,
            ephemeral=True
        )

# ── Основна гра ───────────────────────────────────────────────────────────────

class DuelGame:
    def __init__(self, ch, tg, bet, eco, guild_id):
        self.ch       = ch
        self.tg       = tg
        self.bet      = bet
        self.eco      = eco
        self.guild_id = guild_id
        self.ch_wins  = 0
        self.tg_wins  = 0

    def _score(self) -> str:
        return f"**{self.ch.display_name}** `{self.ch_wins} : {self.tg_wins}` **{self.tg.display_name}**"

    async def run(self, msg: discord.Message):
        curr       = normalize_currency_emoji(self.eco.get("currency_emoji", E_COIN))
        timer      = self.eco.get("duel_timer", self.eco.get("event_timer", 15))
        max_rounds = self.eco.get("duel_max_rounds", 9)
        draw_refund= self.eco.get("duel_draw_refund", True)
        n          = 0

        while self.ch_wins < 3 and self.tg_wins < 3:
            n   += 1
            
            if n > max_rounds and self.ch_wins == self.tg_wins:
                if draw_refund:
                    await db.users.update_one(
                        {"guild_id": self.guild_id, "user_id": self.ch.id},
                        {"$inc": {"wallet": self.bet}}
                    )
                    await db.users.update_one(
                        {"guild_id": self.guild_id, "user_id": self.tg.id},
                        {"$inc": {"wallet": self.bet}}
                    )
                    result_text = f"Ставки повернуто обом гравцям."
                else:
                    result_text = f"Ставки згоріли."
                draw_embed = gameplay_result_embed(
                    "Нічия!",
                    f"Досягнуто ліміт `{max_rounds}` раундів при рівному рахунку\n**{self.ch_wins} : {self.tg_wins}**\n\n{result_text}",
                    tone="warning",
                )
                await msg.edit(embed=draw_embed, view=None)
                return
            rs   = RoundState(self.ch.id, self.tg.id)
            rbv  = RoundButton(self.ch, self.tg, rs)

            # ── Countdown task ────────────────────────────────────────
            async def run_countdown():
                for secs_left in range(timer, 0, -1):
                    if rs.both_chose():
                        break
                    embed = surface_embed(
                        "gameplay",
                        f"Раунд {n}",
                        f"{self._score()}\n\nТисніть **Зробити хід** та оберіть КНП\n⏱ Залишилось: **{secs_left}с**",
                    )
                    try:
                        await msg.edit(embed=embed, view=rbv)
                    except Exception:
                        pass
                    await asyncio.sleep(1)
                rs.event.set()

            countdown_task = asyncio.create_task(run_countdown())

            try:
                await asyncio.wait_for(rs.event.wait(), timeout=timer + 1)
            except asyncio.TimeoutError:
                pass

            countdown_task.cancel()
            try:
                await countdown_task
            except asyncio.CancelledError:
                pass

            if self.ch.id not in rs.choices:
                rs.choices[self.ch.id] = random.choice([ROCK, SCISSORS, PAPER])
            if self.tg.id not in rs.choices:
                rs.choices[self.tg.id] = random.choice([ROCK, SCISSORS, PAPER])

            winner_id, ch_e, tg_e = rs.resolve()

            for uid, mv in rbv.clicked.items():
                asyncio.create_task(mv.close_after_round(ch_e, tg_e, winner_id))

            if winner_id == self.ch.id:
                self.ch_wins += 1
                round_line = f"Раунд виграв **{self.ch.display_name}** {ch_e}"
            elif winner_id == self.tg.id:
                self.tg_wins += 1
                round_line = f"Раунд виграв **{self.tg.display_name}** {tg_e}"
            else:
                round_line = "Нічия в раунді — не рахується"

            # ─ Результат раунду ─
            res_embed = surface_embed(
                "gameplay",
                f"Раунд {n} завершено",
                f"{self.ch.display_name}: {ch_e}  **vs**  {tg_e} :{self.tg.display_name}\n↳ {round_line}\n\n{self._score()}",
                tone="success" if winner_id is not None else "warning",
            )

            next_needed = self.ch_wins < 3 and self.tg_wins < 3
            if next_needed:
                set_surface_footer(res_embed, "gameplay", "Наступний раунд через 3с...")

            await msg.edit(embed=res_embed, view=None)

            if next_needed:
                await asyncio.sleep(3)

        # ── Фінал ─────────────────────────────────────────────────────
        prize  = self.bet * 2
        winner = self.ch if self.ch_wins >= 3 else self.tg
        loser  = self.tg if winner == self.ch else self.ch

        await db.users.update_one(
            {"guild_id": self.guild_id, "user_id": winner.id},
            {
                "$inc": {"wallet": prize, "total_earned": prize},
                "$push": {"eco_history": {"$each": [add_history(prize, f"Дуель: перемога над {loser.display_name}")], "$slice": -50}}
            }
        )
        await db.users.update_one(
            {"guild_id": self.guild_id, "user_id": loser.id},
            {"$push": {"eco_history": {"$each": [add_history(-self.bet, f"Дуель: поразка від {winner.display_name}")], "$slice": -50}}}
        )
        await quest_hook(self.guild_id, winner.id, "duel")
        await quest_hook(self.guild_id, loser.id, "duel")

        final = gameplay_result_embed(
            "Переможець!",
            f"<:trophytop1:1485625873880191067> {winner.mention}\n\n**{self.ch_wins} : {self.tg_wins}**\nПриз: **{prize:,}** {curr}",
            tone="success",
        )
        await msg.edit(embed=final, view=None)

# ── Виклик на дуель ───────────────────────────────────────────────────────────

class ChallengeView(discord.ui.View):
    def __init__(self, challenger, target, bet, eco, guild_id):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.target     = target
        self.bet        = bet
        self.eco        = eco
        self.guild_id   = guild_id
        self.resolved   = False
        self.message: discord.Message | None = None

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.target.id:
            await i.response.send_message("Виклик не тобі!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Прийняти", style=discord.ButtonStyle.success)
    async def accept(self, i: discord.Interaction, _):
        if self.resolved: return
        self.resolved = True
        for c in self.children: c.disabled = True

        curr    = normalize_currency_emoji(self.eco.get("currency_emoji", E_COIN))
        ch_data = await get_user(db, self.guild_id, self.challenger.id)
        tg_data = await get_user(db, self.guild_id, self.target.id)

        if ch_data.get("wallet", 0) < self.bet:
            await i.response.edit_message(
                embed=gameplay_result_embed("Дуель недоступна", f"{E_CROSS} {self.challenger.mention} вже не має достатньо монет.", tone="danger"),
                view=None
            )
            return
        if tg_data.get("wallet", 0) < self.bet:
            await i.response.edit_message(
                embed=gameplay_result_embed("Дуель недоступна", f"{E_CROSS} Тобі бракує **{self.bet:,}** {curr}.", tone="danger"),
                view=None
            )
            return

        await db.users.update_one({"guild_id": self.guild_id, "user_id": self.challenger.id}, {"$inc": {"wallet": -self.bet}})
        await db.users.update_one({"guild_id": self.guild_id, "user_id": self.target.id},     {"$inc": {"wallet": -self.bet}})
        await inc_global_metric("duel_started_total")

        start = surface_embed(
            "gameplay",
            "Камінь Ножиці Папір",
            f"{self.challenger.mention} **vs** {self.target.mention}\nСтавка: **{self.bet:,}** {curr} кожен  •  До **3 перемог**",
        )
        set_surface_footer(start, "gameplay", "Раундовий матч. Обидва гравці роблять прихований вибір.")
        await i.response.edit_message(embed=start, view=None)
        msg = await i.original_response()

        game = DuelGame(self.challenger, self.target, self.bet, self.eco, self.guild_id)
        await game.run(msg)

    @discord.ui.button(label="Відхилити", style=discord.ButtonStyle.secondary)
    async def decline(self, i: discord.Interaction, _):
        if self.resolved: return
        self.resolved = True
        for c in self.children: c.disabled = True
        await i.response.edit_message(
            embed=gameplay_result_embed("Виклик відхилено", f"**{self.target.display_name}** відхилив виклик.", tone="warning"),
            view=None
        )

    async def on_timeout(self):
        if self.resolved:
            return
        self.resolved = True
        for c in self.children:
            c.disabled = True
        if not self.message:
            return
        curr = normalize_currency_emoji(self.eco.get("currency_emoji", E_COIN))
        embed = gameplay_result_embed(
            "Час на прийняття вийшов",
            f"{E_CROSS} {self.target.mention} не прийняв виклик протягом 60 секунд.\n\nСтавка: **{self.bet:,}** {curr} кожен.",
            tone="warning",
        )
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

# ── Команда ───────────────────────────────────────────────────────────────────

class DuelCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="duel", description="Дуель Камінь Ножиці Папір до 3 перемог")
    @app_commands.describe(суперник="Кого викликаєш на дуель", ставка="Скільки монет поставити")
    async def duel(self, interaction: discord.Interaction, суперник: discord.Member, ставка: int):
        settings = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        eco      = get_eco(settings)
        curr     = normalize_currency_emoji(eco.get("currency_emoji", E_COIN))

        if not eco.get("enabled", True):
            await interaction.response.send_message("Економіка вимкнена.", ephemeral=True)
            return
        if суперник.id == interaction.user.id:
            await interaction.response.send_message(f"{E_CROSS} Не можна викликати себе.", ephemeral=True)
            return
        if суперник.bot:
            await interaction.response.send_message(f"{E_CROSS} Боти не грають.", ephemeral=True)
            return
        if ставка <= 0:
            await interaction.response.send_message(f"{E_CROSS} Ставка має бути більше 0.", ephemeral=True)
            return

        ch_data = await get_user(db, interaction.guild.id, interaction.user.id)
        if ch_data.get("wallet", 0) < ставка:
            await interaction.response.send_message(
                f"{E_CROSS} Недостатньо монет. Баланс: **{ch_data.get('wallet', 0):,}** {curr}.",
                ephemeral=True
            )
            return

        embed = surface_embed(
            "gameplay",
            "Виклик на дуель",
            (
                f"{interaction.user.mention} викликає {суперник.mention}\n\n"
                f"Гра: **Камінь Ножиці Папір** · до 3 перемог\n"
                f"Ставка: **{ставка:,}** {curr} кожен\n"
                f"Приз: **{ставка * 2:,}** {curr}\n\n"
                f"*{суперник.mention}, у тебе 60 секунд.*"
            ),
            tone="warning",
        )
        set_surface_footer(embed, "gameplay", "Прийняття запускає раундовий матч із прихованими ходами.")
        view = ChallengeView(interaction.user, суперник, ставка, eco, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(DuelCommand(bot))
