from __future__ import annotations

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from commands.administration.economy_setup_shared import get_eco, normalize_currency_emoji
from commands.economy.events import CRIMES, ROB_STAGE_1, ROB_STAGE_2, ROB_STAGE_3
from commands.economy.minigames import (
    DiceDuelView,
    GuessNumberView,
    HigherLowerView,
    MathQuizView,
    OddEmojiView,
    ReactionTestView,
    ShellGameView,
    TriviaView,
    TypingTestView,
    UnscrambleView,
)
from commands.economy.quests import quest_hook
from config.constants import Emojis as _E
from modules.db import get_database, get_guild_settings, invalidate_user_data
from repositories.user import get_user
from services.metrics import inc_global_metric, inc_global_metrics
from utils.eco_helpers import add_daily_earnings_inc, apply_inflation, check_account_age, fmt_duration, make_log
from utils.ui_contract import gameplay_result_embed, surface_embed

db = get_database()

MINIGAME_BUILDERS = {
    "math": MathQuizView,
    "higher_lower": HigherLowerView,
    "shell": ShellGameView,
    "dice": DiceDuelView,
    "odd_emoji": OddEmojiView,
    "unscramble": UnscrambleView,
    "trivia": TriviaView,
    "typing": TypingTestView,
    "guess": GuessNumberView,
    "reaction": ReactionTestView,
}

ROBBERY_MINIGAMES = {
    "math": {"title": "Розрахунок відходу", "desc": "Прорахуй маршрут і час, поки жертва озирається."},
    "higher_lower": {"title": "Ставка на момент", "desc": "Оціни рух жертви швидше за неї."},
    "shell": {"title": "Де гаманець", "desc": "Стеж за руками жертви й вгадай, у якій кишені здобич."},
    "dice": {"title": "Кидок ва-банк", "desc": "Короткий силовий контакт. Виграй мікродуель."},
    "odd_emoji": {"title": "Озирнись навколо", "desc": "Знайди небезпеку раніше, ніж тебе помітять."},
    "unscramble": {"title": "Шифр для втечі", "desc": "Розбери підказку для маршруту відходу."},
    "trivia": {"title": "Холодний розрахунок", "desc": "Оціни обстановку і вибери правильну дію."},
    "typing": {"title": "Глушилка", "desc": "Швидко введи код глушилки, поки жертва ще не обернулась."},
    "guess": {"title": "Обери момент", "desc": "Піймай правильну секунду для ривка."},
    "reaction": {"title": "Ривок", "desc": "Тисни тільки зелену кнопку. Усе інше — пастки."},
}

BRIBE_SUCCESS_EVENTS = [
    "Патрульний мовчки бере гроші, киває і йде пити каву. Ти вільний.",
    "Купюри зникають у папці слідчого. У протоколі раптом не вистачає доказів.",
    "Коп виявився старим знайомим. За символічну суму він викреслив тебе зі звіту.",
    "Поліцейський бере гроші, але попереджає: ще раз попадешся — ніхто не допоможе.",
]

BRIBE_NEUTRAL_EVENTS = [
    "Офіцер зітхає: камера ввімкнена. Хабар не проходить.",
    "Поліцейський відштовхує гроші і клацає кайданками.",
    "Повз проїжджає наряд. Коп оформлює провал без зайвих слів.",
]

BRIBE_CRITICAL_EVENTS = [
    "Хабар отримує агент під прикриттям. Гроші вилучені, провал подвоюється.",
    "Поліцейський голосно кличе свідків: спроба підкупу зафіксована.",
    "Купюри виявляються міченими. Втрачаєш гроші й отримуєш максимальний тиск.",
]

BRIBE_SPECIAL_EVENTS = [
    "Офіцер бере лише половину і відпускає: зі своїх багато не бере.",
]


def _curr(eco: dict) -> str:
    return normalize_currency_emoji(eco.get("currency_emoji") or _E.COIN.value)


def _game_class(game_type: str):
    return MINIGAME_BUILDERS.get(game_type, GuessNumberView)


def _make_minigame_view(game_type: str, owner_id: int, stake: int, on_complete, *, context: str = "default"):
    game_class = _game_class(game_type)
    if game_class is MathQuizView:
        return game_class(owner_id, stake, on_complete, profile=context)
    return game_class(owner_id, stake, on_complete)


def get_minigame_view(game_type: str, owner_id: int, stake: int, on_complete, context: str = "default"):
    return _make_minigame_view(game_type, owner_id, stake, on_complete, context=context)


def _enabled_operation_games(eco: dict) -> list[str]:
    enabled = set(eco.get("enabled_minigames", list(MINIGAME_BUILDERS)))
    candidates = [game for game in MINIGAME_BUILDERS if game in enabled and any(item.get("minigame") == game for item in CRIMES)]
    return candidates or [game for game in MINIGAME_BUILDERS if any(item.get("minigame") == game for item in CRIMES)]


def _enabled_robbery_games(eco: dict) -> list[str]:
    enabled = set(eco.get("enabled_minigames", list(MINIGAME_BUILDERS)))
    candidates = [game for game in ROBBERY_MINIGAMES if game in enabled]
    return candidates or list(ROBBERY_MINIGAMES)


def _pick_game(candidates: list[str], last_game: str | None) -> str:
    if not candidates:
        return "guess"
    pool = list(candidates)
    if last_game and len(pool) > 1 and last_game in pool:
        pool = [game for game in pool if game != last_game]
    return random.choice(pool)


def _pick_operation_mission(game_type: str) -> dict:
    matching = [item for item in CRIMES if item.get("minigame") == game_type]
    return random.choice(matching) if matching else random.choice(CRIMES)


def _add_minigame_hint(embed: discord.Embed, view, game_type: str):
    if getattr(view, "desc", None):
        embed.description = f"{embed.description}\n\n{view.desc}"
    if getattr(view, "question", None):
        embed.description = f"{embed.description}\n\n**Завдання:** {view.question}"
    if game_type == "reaction":
        embed.description = f"{embed.description}\n\n**Механіка:** тисни тільки зелену кнопку `ТИСНИ`."


async def _swap_message(interaction: discord.Interaction, *, embed: discord.Embed, view: discord.ui.View | None):
    await interaction.response.edit_message(embed=embed, view=view)
    if view is not None:
        try:
            view.message = await interaction.original_response()
        except discord.NotFound:
            view.message = None


class OwnerOnlyView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(f"{_E.CROSS.value} Це не твій вибір.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


class BribeView(OwnerOnlyView):
    def __init__(
        self,
        owner_id: int,
        cmd_interaction: discord.Interaction,
        eco: dict,
        mission_title: str,
        fine: int,
        bribe_sum: int,
        ban_duration: int,
    ):
        super().__init__(owner_id, timeout=eco.get("crime_bribe_timeout", 15))
        self.cmd_interaction = cmd_interaction
        self.eco = eco
        self.mission_title = mission_title
        self.fine = fine
        self.bribe_sum = bribe_sum
        self.ban_duration = ban_duration
        self.handled = False

        pay = discord.ui.Button(
            label=f"Домовитись ({bribe_sum:,})",
            style=discord.ButtonStyle.success,
            emoji=discord.PartialEmoji.from_str(_E.WALLET.value),
        )
        pay.callback = self.on_bribe
        self.add_item(pay)

        penalty = discord.ui.Button(
            label="Прийняти провал",
            style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji.from_str(_E.WARN.value),
        )
        penalty.callback = self.on_penalty
        self.add_item(penalty)

    async def on_timeout(self):
        if self.handled:
            return
        self.handled = True
        await self.apply_penalty(timeout=True)

    async def on_penalty(self, interaction: discord.Interaction):
        self.handled = True
        await self.apply_penalty(interaction=interaction)

    async def on_bribe(self, interaction: discord.Interaction):
        self.handled = True
        await self.process_bribe(interaction)

    async def apply_penalty(self, interaction: discord.Interaction | None = None, *, timeout: bool = False):
        now = int(time.time())
        ban_until = now + self.ban_duration
        await db.users.update_one(
            {"guild_id": self.cmd_interaction.guild.id, "user_id": self.owner_id},
            {
                "$inc": {"wallet": -self.fine},
                "$set": {"crime_last": now, "crime_ban_until": ban_until},
                "$push": {
                    "eco_history": {
                        "$each": [make_log(-self.fine, f"Провал крайму: {self.mission_title}")],
                        "$slice": -50,
                    }
                },
            },
        )
        await inc_global_metric("economy_total_spent", self.fine)
        await invalidate_user_data(self.cmd_interaction.guild.id, self.owner_id)

        embed = gameplay_result_embed(
            f"{_E.CROSS.value} Провал",
            f"Штраф: **{self.fine:,}** {_curr(self.eco)}\nПід слідством: **{fmt_duration(self.ban_duration)}**.",
            tone="danger",
        )
        if timeout:
            embed.description = f"Час на рішення вийшов.\n{embed.description}"

        for child in self.children:
            child.disabled = True

        try:
            if interaction:
                await interaction.response.edit_message(embed=embed, view=self)
            elif self.message:
                await self.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass

    async def process_bribe(self, interaction: discord.Interaction):
        now = int(time.time())
        roll = random.random()
        currency = _curr(self.eco)

        if roll < 0.40:
            result = await db.users.find_one_and_update(
                {
                    "guild_id": self.cmd_interaction.guild.id,
                    "user_id": self.owner_id,
                    "wallet": {"$gte": self.bribe_sum},
                },
                {
                    "$inc": {"wallet": -self.bribe_sum},
                    "$set": {"crime_last": now},
                    "$unset": {"crime_ban_until": ""},
                    "$push": {
                        "eco_history": {
                            "$each": [make_log(-self.bribe_sum, f"Хабар: {self.mission_title}")],
                            "$slice": -50,
                        }
                    },
                },
            )
            if not result:
                return await self.apply_penalty(interaction)
            await inc_global_metric("economy_total_spent", self.bribe_sum)
            await invalidate_user_data(self.cmd_interaction.guild.id, self.owner_id)
            text = random.choice(BRIBE_SUCCESS_EVENTS)
            embed = gameplay_result_embed(
                f"{_E.CHECK.value} Питання вирішено",
                f"{text}\n\nВитрачено: **{self.bribe_sum:,}** {currency}",
                tone="success",
            )
        elif roll < 0.80:
            text = random.choice(BRIBE_NEUTRAL_EVENTS)
            await self.apply_penalty(interaction)
            if interaction.response.is_done():
                pass
            return
        elif roll < 0.95:
            ban_duration = self.ban_duration * 2
            ban_until = now + ban_duration
            result = await db.users.find_one_and_update(
                {
                    "guild_id": self.cmd_interaction.guild.id,
                    "user_id": self.owner_id,
                    "wallet": {"$gte": self.bribe_sum},
                },
                {
                    "$inc": {"wallet": -self.bribe_sum},
                    "$set": {"crime_last": now, "crime_ban_until": ban_until},
                    "$push": {
                        "eco_history": {
                            "$each": [make_log(-self.bribe_sum, f"Критичний провал хабаря: {self.mission_title}")],
                            "$slice": -50,
                        }
                    },
                },
            )
            if not result:
                return await self.apply_penalty(interaction)
            await inc_global_metric("economy_total_spent", self.bribe_sum)
            await invalidate_user_data(self.cmd_interaction.guild.id, self.owner_id)
            text = random.choice(BRIBE_CRITICAL_EVENTS)
            embed = gameplay_result_embed(
                f"{_E.CROSS.value} Критичний провал",
                f"{text}\n\nВтрачено: **{self.bribe_sum:,}** {currency}\nПід слідством: **{fmt_duration(ban_duration)}**.",
                tone="danger",
            )
        else:
            half = max(1, self.bribe_sum // 2)
            result = await db.users.find_one_and_update(
                {
                    "guild_id": self.cmd_interaction.guild.id,
                    "user_id": self.owner_id,
                    "wallet": {"$gte": half},
                },
                {
                    "$inc": {"wallet": -half},
                    "$set": {"crime_last": now},
                    "$unset": {"crime_ban_until": ""},
                    "$push": {
                        "eco_history": {
                            "$each": [make_log(-half, f"Половина хабаря: {self.mission_title}")],
                            "$slice": -50,
                        }
                    },
                },
            )
            if not result:
                return await self.apply_penalty(interaction)
            await inc_global_metric("economy_total_spent", half)
            await invalidate_user_data(self.cmd_interaction.guild.id, self.owner_id)
            text = random.choice(BRIBE_SPECIAL_EVENTS)
            embed = gameplay_result_embed(
                f"{_E.CHECK.value} Домовились",
                f"{text}\n\nВитрачено: **{half:,}** {currency}",
                tone="success",
            )

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)


class CrimeModeView(OwnerOnlyView):
    def __init__(self, cog: "CrimeCommand", owner_id: int, eco: dict):
        super().__init__(owner_id, timeout=300)
        self.cog = cog
        self.eco = eco
        self.operation_btn.disabled = not eco.get("crime_enabled", True)
        self.robbery_btn.disabled = not eco.get("rob_enabled", True)

    @discord.ui.button(label="Операція", style=discord.ButtonStyle.primary)
    async def operation_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.start_operation(interaction, self.eco)

    @discord.ui.button(label="Пограбування", style=discord.ButtonStyle.secondary)
    async def robbery_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.open_robbery_picker(interaction, self.eco)


class RobberyTargetSelect(discord.ui.UserSelect):
    def __init__(self, parent: "RobberyTargetView"):
        super().__init__(placeholder="Обери жертву для пограбування...", min_values=1, max_values=1)
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.on_target_selected(interaction, self.values[0])


class RobberyTargetView(OwnerOnlyView):
    def __init__(self, cog: "CrimeCommand", owner_id: int, eco: dict):
        super().__init__(owner_id, timeout=300)
        self.cog = cog
        self.eco = eco
        self.add_item(RobberyTargetSelect(self))

    async def on_target_selected(self, interaction: discord.Interaction, target: discord.Member | discord.User):
        await self.cog.preview_robbery(interaction, self.eco, target)

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(_E.BACK.value))
    async def back_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.show_mode_picker(interaction, self.eco)


class RobberyConfirmView(OwnerOnlyView):
    def __init__(self, cog: "CrimeCommand", owner_id: int, eco: dict, target_id: int):
        super().__init__(owner_id, timeout=180)
        self.cog = cog
        self.eco = eco
        self.target_id = target_id

    @discord.ui.button(label="Почати пограбування", style=discord.ButtonStyle.danger, emoji=discord.PartialEmoji.from_str(_E.ROBBERY.value))
    async def start_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.start_robbery(interaction, self.eco, self.target_id)

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(_E.BACK.value))
    async def back_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.open_robbery_picker(interaction, self.eco)


class CrimeCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _load_eco(self, guild_id: int) -> dict:
        settings = await get_guild_settings(db, guild_id)
        return get_eco(settings)

    def _build_mode_embed(self) -> discord.Embed:
        return surface_embed("admin", f"{_E.MASK.value} Крайм", "Оберіть режим.")

    async def show_mode_picker(self, interaction: discord.Interaction, eco: dict):
        embed = self._build_mode_embed()
        view = CrimeModeView(self, interaction.user.id, eco)
        await _swap_message(interaction, embed=embed, view=view)

    async def _check_operation_access(self, interaction: discord.Interaction, eco: dict):
        if not eco.get("enabled", True):
            await interaction.response.send_message(f"{_E.CROSS.value} Економіка вимкнена на цьому сервері.", ephemeral=True)
            return None
        if not eco.get("crime_enabled", True):
            await interaction.response.send_message(f"{_E.CROSS.value} Режим операцій вимкнений адміністратором.", ephemeral=True)
            return None
        if not await check_account_age(interaction, eco):
            return None

        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        now = int(time.time())
        crime_ban = user_data.get("crime_ban_until", 0)
        if crime_ban and now < crime_ban:
            await interaction.response.send_message(
                f"{_E.CROSS.value} Ти під слідством. Звільнення через **{fmt_duration(crime_ban - now)}**.",
                ephemeral=True,
            )
            return None

        cooldown = eco.get("crime_cooldown", 28800)
        crime_last = user_data.get("crime_last", 0)
        if crime_last and (now - crime_last) < cooldown:
            await interaction.response.send_message(
                f"{_E.HOURGLASS.value} Наступна операція доступна через **{fmt_duration(int(cooldown - (now - crime_last)))}**.",
                ephemeral=True,
            )
            return None

        return user_data

    async def _check_robbery_access(self, interaction: discord.Interaction, eco: dict):
        if not eco.get("enabled", True):
            await interaction.response.send_message(f"{_E.CROSS.value} Економіка вимкнена на цьому сервері.", ephemeral=True)
            return None
        if not eco.get("rob_enabled", True):
            await interaction.response.send_message(f"{_E.CROSS.value} Режим пограбування вимкнений адміністратором.", ephemeral=True)
            return None
        if not await check_account_age(interaction, eco):
            return None

        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        now = int(time.time())
        rob_last = user_data.get("rob_last", 0)
        rob_cooldown = eco.get("rob_cooldown", 3600)
        if rob_last and (now - rob_last) < rob_cooldown:
            await interaction.response.send_message(
                f"{_E.HOURGLASS.value} Наступне пограбування доступне через **{fmt_duration(int(rob_cooldown - (now - rob_last)))}**.",
                ephemeral=True,
            )
            return None
        return user_data

    async def start_operation(self, interaction: discord.Interaction, eco: dict):
        user_data = await self._check_operation_access(interaction, eco)
        if user_data is None:
            return

        candidates = _enabled_operation_games(eco)
        game_type = _pick_game(candidates, user_data.get("crime_last_minigame"))
        mission = _pick_operation_mission(game_type)
        work_max = eco.get("work_max", 500)
        potential_reward = int(random.randint(int(work_max * 3), int(work_max * 6)))
        currency = _curr(eco)
        now = int(time.time())

        async def on_complete(i: discord.Interaction | None, outcome: str, result_embed: discord.Embed, game_view):
            if outcome == "win":
                earned = potential_reward
                boost_active = now < user_data.get("coin_boost_until", 0)
                if boost_active:
                    earned *= 2

                inc_query = {"wallet": earned, "total_earned": earned}
                add_daily_earnings_inc(inc_query, earned, timestamp=now)

                await db.users.update_one(
                    {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                    {
                        "$inc": inc_query,
                        "$set": {"crime_last": int(time.time()), "crime_last_minigame": game_type},
                        "$push": {"eco_history": {"$each": [make_log(earned, f"Крайм: {mission['title']}")], "$slice": -50}},
                    },
                )
                await inc_global_metrics({"crime_runs_total": 1, "crime_success_total": 1, "economy_total_earned": earned})
                await quest_hook(interaction.guild.id, interaction.user.id, "crime")
                await apply_inflation(db, interaction.guild.id, earned, eco)
                await invalidate_user_data(interaction.guild.id, interaction.user.id)

                result_embed.title = f"{_E.CHECK.value} Операція пройшла успішно"
                result_embed.description = (
                    f"{result_embed.description}\n\nОтримано: **{earned:,}** {currency}"
                    + ("\nБуст монет активний: нагороду подвоєно." if boost_active else "")
                )
                result_embed.color = discord.Color.green()
                if i:
                    await i.response.edit_message(embed=result_embed, view=None)
                elif getattr(game_view, "message", None):
                    await game_view.message.edit(embed=result_embed, view=None)
                return

            if outcome == "draw":
                await db.users.update_one(
                    {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                    {"$set": {"crime_last": int(time.time()), "crime_last_minigame": game_type}},
                )
                await inc_global_metric("crime_runs_total", 1)
                await invalidate_user_data(interaction.guild.id, interaction.user.id)
                result_embed.title = f"{_E.WARN.value} Тимчасове затишшя"
                result_embed.description = f"{result_embed.description}\n\nТи відступив без здобичі, але й без покарання."
                result_embed.color = discord.Color.yellow()
                if i:
                    await i.response.edit_message(embed=result_embed, view=None)
                elif getattr(game_view, "message", None):
                    await game_view.message.edit(embed=result_embed, view=None)
                return

            wallet = user_data.get("wallet", 0)
            fine = min(wallet, int(potential_reward * 0.4))
            ban_duration = eco.get("crime_ban_duration", 1800)
            bribe_sum = int(potential_reward * (eco.get("crime_bribe_percent", 75) / 100))
            await inc_global_metric("crime_runs_total", 1)

            if wallet < bribe_sum:
                ban_until = int(time.time()) + ban_duration
                await db.users.update_one(
                    {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                    {
                        "$inc": {"wallet": -fine},
                        "$set": {"crime_last": int(time.time()), "crime_ban_until": ban_until, "crime_last_minigame": game_type},
                        "$push": {"eco_history": {"$each": [make_log(-fine, f"Провал крайму: {mission['title']}")], "$slice": -50}},
                    },
                )
                await inc_global_metric("economy_total_spent", fine)
                await invalidate_user_data(interaction.guild.id, interaction.user.id)
                result_embed.title = f"{_E.CROSS.value} Провал операції"
                result_embed.description = (
                    f"{result_embed.description}\n\nШтраф: **{fine:,}** {currency}\nПід слідством: **{fmt_duration(ban_duration)}**."
                )
                result_embed.color = discord.Color.red()
                if i:
                    await i.response.edit_message(embed=result_embed, view=None)
                elif getattr(game_view, "message", None):
                    await game_view.message.edit(embed=result_embed, view=None)
                return

            bribe_view = BribeView(interaction.user.id, interaction, eco, mission["title"], fine, bribe_sum, ban_duration)
            result_embed.title = f"{_E.CROSS.value} Провал операції"
            result_embed.description = (
                f"{result_embed.description}\n\nТебе спіймали. У тебе є **{eco.get('crime_bribe_timeout', 15)}с**, щоб спробувати домовитись."
            )
            result_embed.color = discord.Color.red()
            if i:
                await i.response.edit_message(embed=result_embed, view=bribe_view)
                bribe_view.message = await i.original_response()
            elif getattr(game_view, "message", None):
                await game_view.message.edit(embed=result_embed, view=bribe_view)
                bribe_view.message = game_view.message

        view = _make_minigame_view(game_type, interaction.user.id, potential_reward, on_complete, context="crime")
        embed = surface_embed("admin", mission["title"], mission["desc"])
        _add_minigame_hint(embed, view, game_type)
        await _swap_message(interaction, embed=embed, view=view)

    async def open_robbery_picker(self, interaction: discord.Interaction, eco: dict):
        user_data = await self._check_robbery_access(interaction, eco)
        if user_data is None:
            return

        embed = surface_embed("admin", f"{_E.ROBBERY.value} Пограбування", "Оберіть ціль.")
        view = RobberyTargetView(self, interaction.user.id, eco)
        await _swap_message(interaction, embed=embed, view=view)

    async def preview_robbery(self, interaction: discord.Interaction, eco: dict, target: discord.Member | discord.User):
        robber_data = await self._check_robbery_access(interaction, eco)
        if robber_data is None:
            return

        if target.id == interaction.user.id:
            await interaction.response.send_message(f"{_E.CROSS.value} Себе грабувати не можна.", ephemeral=True)
            return
        if target.bot:
            await interaction.response.send_message(f"{_E.CROSS.value} Ботів грабувати не можна.", ephemeral=True)
            return

        victim_data = await get_user(db, interaction.guild.id, target.id)
        victim_wallet = victim_data.get("wallet", 0)
        if victim_wallet < 10:
            await interaction.response.send_message(f"{_E.CROSS.value} У {target.mention} майже порожній гаманець.", ephemeral=True)
            return
        if victim_data.get("shield_until", 0) > int(time.time()):
            await interaction.response.send_message(f"{_E.CROSS.value} У {target.mention} активний щит.", ephemeral=True)
            return

        pct_min = eco.get("rob_percent_min", 10)
        pct_max = eco.get("rob_percent_max", 40)
        possible_min = max(1, int(victim_wallet * pct_min / 100))
        possible_max = max(possible_min, int(victim_wallet * pct_max / 100))
        fail_fine = max(1, int(robber_data.get("wallet", 0) * (eco.get("rob_fine_percent", 25) / 100)))

        embed = surface_embed("admin", f"{_E.ROBBERY.value} Ціль: {target.display_name}", "Ризик і наслідки перед стартом.")
        embed.add_field(name="Ризик успіху", value=f"**{eco.get('rob_chance', 40)}%**", inline=True)
        embed.add_field(name="Можлива здобич", value=f"**{possible_min:,} – {possible_max:,}** {_curr(eco)}", inline=True)
        embed.add_field(name="Штраф за провал", value=f"**{fail_fine:,}** {_curr(eco)}", inline=True)

        view = RobberyConfirmView(self, interaction.user.id, eco, target.id)
        await _swap_message(interaction, embed=embed, view=view)

    async def start_robbery(self, interaction: discord.Interaction, eco: dict, target_id: int):
        robber_data = await self._check_robbery_access(interaction, eco)
        if robber_data is None:
            return

        target = interaction.guild.get_member(target_id)
        if not target or target.bot:
            await interaction.response.send_message(f"{_E.CROSS.value} Ціль більше недоступна.", ephemeral=True)
            return
        if target.id == interaction.user.id:
            await interaction.response.send_message(f"{_E.CROSS.value} Себе грабувати не можна.", ephemeral=True)
            return

        victim_data = await get_user(db, interaction.guild.id, target.id)
        now = int(time.time())
        if victim_data.get("shield_until", 0) > now:
            await interaction.response.send_message(f"{_E.CROSS.value} У {target.mention} активний щит.", ephemeral=True)
            return

        victim_wallet = victim_data.get("wallet", 0)
        if victim_wallet < 10:
            await interaction.response.send_message(f"{_E.CROSS.value} У {target.mention} замало грошей для пограбування.", ephemeral=True)
            return

        candidates = _enabled_robbery_games(eco)
        game_type = _pick_game(candidates, robber_data.get("rob_last_minigame"))
        scene = ROBBERY_MINIGAMES[game_type]
        currency = _curr(eco)

        async def on_complete(i: discord.Interaction | None, outcome: str, result_embed: discord.Embed, game_view):
            if outcome == "win":
                pct = random.randint(eco.get("rob_percent_min", 10), eco.get("rob_percent_max", 40))
                stolen = max(1, int(victim_wallet * pct / 100))
                victim_result = await db.users.find_one_and_update(
                    {"guild_id": interaction.guild.id, "user_id": target.id, "wallet": {"$gte": stolen}},
                    {
                        "$inc": {"wallet": -stolen},
                        "$push": {"eco_history": {"$each": [make_log(-stolen, f"Пограбований: {interaction.user.display_name}")], "$slice": -50}},
                    },
                )
                if not victim_result:
                    result_embed.title = f"{_E.CROSS.value} Провал пограбування"
                    result_embed.description = "Жертва встигла сховати гроші раніше за тебе."
                    result_embed.color = discord.Color.red()
                    await db.users.update_one(
                        {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                        {"$set": {"rob_last": int(time.time()), "rob_last_minigame": game_type}},
                    )
                    await invalidate_user_data(interaction.guild.id, interaction.user.id)
                    if i:
                        await i.response.edit_message(embed=result_embed, view=None)
                    elif getattr(game_view, "message", None):
                        await game_view.message.edit(embed=result_embed, view=None)
                    return

                await db.users.update_one(
                    {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                    {
                        "$inc": {"wallet": stolen},
                        "$set": {"rob_last": int(time.time()), "rob_last_minigame": game_type},
                        "$push": {"eco_history": {"$each": [make_log(stolen, f"Пограбування: {target.display_name}")], "$slice": -50}},
                    },
                )
                await invalidate_user_data(interaction.guild.id, interaction.user.id)
                await invalidate_user_data(interaction.guild.id, target.id)
                await inc_global_metrics({"crime_runs_total": 1, "crime_success_total": 1})
                await quest_hook(interaction.guild.id, interaction.user.id, "crime")

                result_embed.title = f"{_E.CHECK.value} Пограбування вдалося"
                result_embed.description = (
                    f"{result_embed.description}\n\nЖертва: **{target.display_name}**\n"
                    f"Вкрадено: **{stolen:,}** {currency} ({pct}%)."
                )
                result_embed.color = discord.Color.green()
                if i:
                    await i.response.edit_message(embed=result_embed, view=None)
                elif getattr(game_view, "message", None):
                    await game_view.message.edit(embed=result_embed, view=None)
                return

            if outcome == "draw":
                await db.users.update_one(
                    {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                    {"$set": {"rob_last": int(time.time()), "rob_last_minigame": game_type}},
                )
                await inc_global_metric("crime_runs_total", 1)
                await invalidate_user_data(interaction.guild.id, interaction.user.id)
                result_embed.title = f"{_E.WARN.value} Пограбування зірвалось"
                result_embed.description = f"{result_embed.description}\n\nТи втік без здобичі, але без прямого штрафу."
                result_embed.color = discord.Color.yellow()
                if i:
                    await i.response.edit_message(embed=result_embed, view=None)
                elif getattr(game_view, "message", None):
                    await game_view.message.edit(embed=result_embed, view=None)
                return

            fine = max(1, int(robber_data.get("wallet", 0) * (eco.get("rob_fine_percent", 25) / 100)))
            await db.users.update_one(
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                {
                    "$inc": {"wallet": -fine},
                    "$set": {"rob_last": int(time.time()), "rob_last_minigame": game_type},
                    "$push": {"eco_history": {"$each": [make_log(-fine, f"Невдале пограбування: {target.display_name}")], "$slice": -50}},
                },
            )
            await inc_global_metrics({"crime_runs_total": 1, "economy_total_spent": fine})
            await invalidate_user_data(interaction.guild.id, interaction.user.id)
            result_embed.title = f"{_E.CROSS.value} Пограбування провалилось"
            result_embed.description = (
                f"{result_embed.description}\n\nЖертва: **{target.display_name}**\nШтраф: **{fine:,}** {currency}."
            )
            result_embed.color = discord.Color.red()
            if i:
                await i.response.edit_message(embed=result_embed, view=None)
            elif getattr(game_view, "message", None):
                await game_view.message.edit(embed=result_embed, view=None)

        view = _make_minigame_view(game_type, interaction.user.id, victim_wallet, on_complete, context="crime")
        stage_1 = random.choice(ROB_STAGE_1).format(target=target.display_name)
        stage_2 = random.choice(ROB_STAGE_2).format(target=target.display_name)
        stage_3 = random.choice(ROB_STAGE_3).format(target=target.display_name)
        embed = surface_embed("admin", f"{_E.ROBBERY.value} {scene['title']}", f"{stage_1}\n{stage_2}\n\n{scene['desc']}\n\n{stage_3}")
        _add_minigame_hint(embed, view, game_type)
        await _swap_message(interaction, embed=embed, view=view)

    @app_commands.command(name="crime", description="Ризикована кримінальна операція")
    async def crime(self, interaction: discord.Interaction):
        eco = await self._load_eco(interaction.guild.id)
        if not eco.get("enabled", True):
            await interaction.response.send_message(f"{_E.CROSS.value} Економіка вимкнена на цьому сервері.", ephemeral=True)
            return
        if not eco.get("crime_enabled", True) and not eco.get("rob_enabled", True):
            await interaction.response.send_message(f"{_E.CROSS.value} Усі режими крайму вимкнені адміністратором.", ephemeral=True)
            return

        embed = self._build_mode_embed()
        view = CrimeModeView(self, interaction.user.id, eco)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()


async def setup(bot):
    await bot.add_cog(CrimeCommand(bot))
