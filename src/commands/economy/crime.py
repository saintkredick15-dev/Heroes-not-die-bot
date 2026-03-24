from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import time
import random

from modules.db import get_database
from repositories.user import get_user
from commands.administration.economy_setup import get_eco
from commands.economy.events import CRIMES
from commands.economy.quests import quest_hook
from utils.eco_helpers import make_log, apply_inflation, fmt_duration
from utils.ui_contract import gameplay_result_embed, set_surface_footer, surface_embed
from commands.economy.minigames import (
    MathQuizView, HigherLowerView, ShellGameView, DiceDuelView,
    OddEmojiView, UnscrambleView, TriviaView, TypingTestView,
    GuessNumberView, ReactionTestView
)
from commands.economy.events import CRIMES

E_COIN = "<:coin:1485610808003133552>"
db = get_database()

def get_minigame_view(
    game_type: str,
    owner_id: int,
    stake: int,
    on_complete,
    context: str = "default",
):

    games = {
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
        "highlow": HigherLowerView,  
    }
    game_class = games.get(game_type, GuessNumberView)  
    if game_class is MathQuizView:
        return game_class(owner_id, stake, on_complete, profile=context)
    return game_class(owner_id, stake, on_complete)

class BribeView(discord.ui.View):
    def __init__(self, owner_id: int, cmd_interaction: discord.Interaction, eco: dict, user_data: dict, mission: dict, potential_reward: int, fine: int, bribe_sum: int, ban_dur: int):
        bribe_timeout = eco.get("crime_bribe_timeout", 15)
        super().__init__(timeout=bribe_timeout)
        self.owner_id = owner_id
        self.cmd_interaction = cmd_interaction
        self.eco = eco
        self.user_data = user_data
        self.mission = mission
        self.fine = fine
        self.bribe_sum = bribe_sum
        self.ban_dur = ban_dur
        self.curr = eco.get("currency_emoji", E_COIN)
        self.message = None
        self.handled = False
        
        btn_bribe = discord.ui.Button(label=f"Домовитись ({bribe_sum:,})", style=discord.ButtonStyle.success, emoji="<:wallet:1485625593574850720>")
        btn_bribe.callback = self.on_bribe
        self.add_item(btn_bribe)
        
        btn_penalty = discord.ui.Button(label="Покарання", style=discord.ButtonStyle.danger, emoji="<:warning:1485598476850040843>")
        btn_penalty.callback = self.on_penalty
        self.add_item(btn_penalty)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Це не ваш вибір!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.handled: return
        self.handled = True
        await self.apply_penalty(timeout=True)

    async def on_penalty(self, interaction: discord.Interaction):
        self.handled = True
        await self.apply_penalty(interaction=interaction)

    async def on_bribe(self, interaction: discord.Interaction):
        self.handled = True
        await self.process_bribe(interaction)

    async def apply_penalty(self, interaction: discord.Interaction = None, timeout: bool = False):
        ban_until = int(time.time()) + self.ban_dur
        await db.users.update_one(
            {"guild_id": self.cmd_interaction.guild.id, "user_id": self.owner_id},
            {
                "$inc": {"wallet": -self.fine},
                "$set": {"crime_last": int(time.time()), "crime_ban_until": ban_until},
                "$push": {"eco_history": {"$each": [make_log(-self.fine, f"Провал крайму: {self.mission['title']}")], "$slice": -50}}
            }
        )
        embed = gameplay_result_embed("🚨 Провал", f"{E_CROSS} Знято штраф: **{self.fine:,}** {self.curr}\nТи під слідством на **{fmt_duration(self.ban_dur)}**.", tone="danger")
        if timeout:
            embed.description = f"⏱ Час на обдумування вийшов.\n{embed.description}"
            
        for child in self.children: child.disabled = True
        try:
            if interaction:
                await interaction.response.edit_message(embed=embed, view=self)
            elif self.message:
                await self.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass

    async def process_bribe(self, interaction: discord.Interaction):
        success_events = [
            "Патрульний мовчки бере гроші, киває і йде пити каву. Ви вільні.",
            "Ви сунули купюри в папку слідчого. Він посміхнувся: 'Яких доказів? Я нічого не бачив'.",
            "Поліцейський виявився вашим старим знайомим. За 'символічну плату' він викреслив вас зі звіту.",
            "Коп взяв гроші, але попередив: 'Ще раз попадешся в мою зміну — сядеш надовго'."
        ]
        neutral_events = [
            "Офіцер зітхнув: 'Я б узяв, але в мене нагрудна камера увімкнена'. Вас заарештовано.",
            "Поліцейський обурено відштовхнув гроші: 'Я чесний коп! Руки за спину!'.",
            "Ви спробували дати на лапу, але повз проїжджав наряд. Коп зробив вигляд, що нічого не помітив, і одягнув кайданки."
        ]
        critical_events = [
            "Ви дали хабар... агенту ФБР під прикриттям. Гроші вилучено, вам інкримінують підкуп!",
            "Поліцейський крикнув 'Він пропонує хабар!'. Гроші конфісковані як речовий доказ.",
            "Ваші купюри виявилися міченими. Копи забрали гроші і впаяли вам максимальний термін!"
        ]
        special_events = [
            "Ви дали хабар, але офіцер відщипнув половину і повернув решту: 'Зі своїх багато не беру'.",
        ]

        r = random.random()
        if r < 0.40: 
            ev = random.choice(success_events)
            result = await db.users.find_one_and_update(
                {"guild_id": self.cmd_interaction.guild.id, "user_id": self.owner_id, "wallet": {"$gte": self.bribe_sum}},
                {
                    "$inc": {"wallet": -self.bribe_sum},
                    "$set": {"crime_last": int(time.time())},
                    "$push": {"eco_history": {"$each": [make_log(-self.bribe_sum, f"Хабар: {self.mission['title']}")], "$slice": -50}}
                }
            )
            if not result:
                return await self.apply_penalty(interaction, timeout=False)
            
            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, self.owner_id)

            embed = gameplay_result_embed("🤝 Питання вирішено", f"{ev}\n\nВитрачено хабар: **{self.bribe_sum:,}** {self.curr}", tone="success")
        elif r < 0.80: 
            ev = random.choice(neutral_events)
            ban_until = int(time.time()) + self.ban_dur
            await db.users.update_one(
                {"guild_id": self.cmd_interaction.guild.id, "user_id": self.owner_id},
                {
                    "$inc": {"wallet": -self.fine}, 
                    "$set": {"crime_last": int(time.time()), "crime_ban_until": ban_until},
                    "$push": {"eco_history": {"$each": [make_log(-self.fine, f"Провал крайму: {self.mission['title']}")], "$slice": -50}}
                }
            )
            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, self.owner_id)

            embed = gameplay_result_embed("🚨 Хабар не пройшов", f"{ev}\n\nЗнято штраф: **{self.fine:,}** {self.curr}\nТи під слідством на **{fmt_duration(self.ban_dur)}**.", tone="danger")
        elif r < 0.95: 
            ev = random.choice(critical_events)
            ban_until = int(time.time()) + (self.ban_dur * 2)
            result = await db.users.find_one_and_update(
                {"guild_id": self.cmd_interaction.guild.id, "user_id": self.owner_id, "wallet": {"$gte": self.bribe_sum}},
                {
                    "$inc": {"wallet": -self.bribe_sum},
                    "$set": {"crime_last": int(time.time()), "crime_ban_until": ban_until},
                    "$push": {"eco_history": {"$each": [make_log(-self.bribe_sum, f"Підкуп ФБР: {self.mission['title']}")], "$slice": -50}}
                }
            )
            if not result:
                return await self.apply_penalty(interaction, timeout=False)

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, self.owner_id)

            embed = gameplay_result_embed("⛓️ Критичний провал!", f"{ev}\n\nВтрачено хабар: **{self.bribe_sum:,}** {self.curr}\nТи під слідством на **{fmt_duration(self.ban_dur * 2)}**.", tone="danger")
        else: 
            ev = random.choice(special_events)
            half = self.bribe_sum // 2
            result = await db.users.find_one_and_update(
                {"guild_id": self.cmd_interaction.guild.id, "user_id": self.owner_id, "wallet": {"$gte": half}},
                {
                    "$inc": {"wallet": -half},
                    "$set": {"crime_last": int(time.time())},
                    "$push": {"eco_history": {"$each": [make_log(-half, f"Половина хабаря: {self.mission['title']}")], "$slice": -50}}
                }
            )
            if not result:
                return await self.apply_penalty(interaction, timeout=False)

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, self.owner_id)

            embed = gameplay_result_embed("🤝 Питання успішно вирішено", f"{ev}\n\nВитрачено: **{half:,}** {self.curr}", tone="success")
            
        for child in self.children: child.disabled = True
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.NotFound:
            pass

class CrimeCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crime", description="Ризикована кримінальна операція")
    async def crime(self, interaction: discord.Interaction):
        try:
            from modules.db import get_guild_settings
            settings  = await get_guild_settings(db, interaction.guild.id)
            eco       = get_eco(settings)

            if not eco.get("enabled", True):
                await interaction.response.send_message(f"{E_CROSS} Економіка вимкнена.", ephemeral=True)
                return
            if not eco.get("crime_enabled", True):
                await interaction.response.send_message(f"{E_CROSS} Команда /crime вимкнена адміністратором.", ephemeral=True)
                return

            user_data  = await get_user(db, interaction.guild.id, interaction.user.id)
            now        = int(time.time())
            cooldown   = eco.get("crime_cooldown", 28800)
            crime_last = user_data.get("crime_last", 0)

            crime_ban = user_data.get("crime_ban_until", 0)
            if crime_ban and now < crime_ban:
                remaining = crime_ban - now
                if remaining > 0:
                    await interaction.response.send_message(
                        f"{E_CROSS} Ти під слідством. Звільняєшся через **{fmt_duration(remaining)}**.",
                        ephemeral=True
                    )
                    return

            if crime_last and (now - crime_last) < cooldown:
                remaining = int(cooldown - (now - crime_last))
                await interaction.response.send_message(
                    f"<:hourglass:1485598603937579181> Наступна операція доступна через **{fmt_duration(remaining)}**.",
                    ephemeral=True
                )
                return

            mission    = random.choice(CRIMES)
            curr       = eco.get("currency_emoji", E_COIN)
            work_max   = eco.get("work_max", 500)
            
            potential_reward = int(random.randint(int(work_max * 3), int(work_max * 6)))

            embed = surface_embed("gameplay", f"🚨 {mission['title']}", mission['desc'], tone="warning")
            set_surface_footer(embed, "gameplay", "Починаємо операцію. Далі буде інтерактивне випробування.")

            async def on_minigame_complete(i: discord.Interaction, outcome: str, res_embed: discord.Embed, game_view):
                
                if outcome == "win":
                    earned = potential_reward
                    boost_active = now < user_data.get("coin_boost_until", 0)
                    if boost_active:
                        earned = earned * 2

                    log = make_log(earned, f"Крайм: {mission['title']}")
                    await db.users.update_one(
                        {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                        {
                            "$inc": {"wallet": earned, "total_earned": earned},
                            "$set": {"crime_last": int(time.time())},
                            "$push": {"eco_history": {"$each": [log], "$slice": -50}}
                        }
                    )
                    await quest_hook(interaction.guild.id, interaction.user.id, "crime")
                    await apply_inflation(db, interaction.guild.id, earned, eco)

                    from modules.db import invalidate_user_data
                    await invalidate_user_data(interaction.guild.id, interaction.user.id)
                    
                    res_embed.title = "<:check:1485597845883981905> Операція пройшла успішно!"
                    res_embed.description = f"{res_embed.description}\n\nОтримано: **{earned:,}** {curr}" + ("\n🌟 **Coin Boost x2** активний!" if boost_active else "")
                    res_embed.color = COLOR_WIN

                elif outcome == "draw":
                    await db.users.update_one(
                        {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                        {"$set": {"crime_last": int(time.time())}}
                    )
                    res_embed.title = "🤝 Тимчасове затишшя"
                    res_embed.description = f"{res_embed.description}\n\nВирішено відступити без здобичі, але й без покарання."
                    res_embed.color = 0xffff00

                else:
                    wallet     = user_data.get("wallet", 0)
                    fine       = min(wallet, int(potential_reward * 0.4)) 
                    ban_dur    = eco.get("crime_ban_duration", 1800)
                    bribe_sum  = int(potential_reward * (eco.get("crime_bribe_percent", 75) / 100))

                    if wallet < bribe_sum:
                        ban_until = int(time.time()) + ban_dur
                        await db.users.update_one(
                            {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                            {
                                "$inc": {"wallet": -fine},
                                "$set": {"crime_last": int(time.time()), "crime_ban_until": ban_until},
                                "$push": {"eco_history": {"$each": [make_log(-fine, f"Провал крайму: {mission['title']}")], "$slice": -50}}
                            }
                        )

                        from modules.db import invalidate_user_data
                        await invalidate_user_data(interaction.guild.id, interaction.user.id)

                        res_embed.title = "🚨 Провал операції!"
                        res_embed.description = (f"{res_embed.description}\n\n{E_CROSS} Знято штраф: **{fine:,}** {curr}\n"
                                                 f"Ти під слідством на **{fmt_duration(ban_dur)}**.")
                        res_embed.color = COLOR_LOSE
                        
                        if getattr(game_view, "message", None):
                            await game_view.message.edit(embed=res_embed, view=None)
                        elif i and not i.response.is_done():
                            await i.response.edit_message(embed=res_embed, view=None)
                        elif i:
                            await i.followup.edit_message(i.message.id, embed=res_embed, view=None)
                    else:
                        bribe_view = BribeView(interaction.user.id, interaction, eco, user_data, mission, potential_reward, fine, bribe_sum, ban_dur)
                        
                        res_embed.title = "🚨 Провал операції!"
                        res_embed.description = (f"{res_embed.description}\n\nВас спіймали! У вас є **{eco.get('crime_bribe_timeout', 15)}с**, щоб спробувати домовитись...")
                        res_embed.color = COLOR_LOSE
                        
                        if getattr(game_view, "message", None):
                            await game_view.message.edit(embed=res_embed, view=bribe_view)
                            bribe_view.message = game_view.message
                        elif i and not i.response.is_done():
                            await i.response.edit_message(embed=res_embed, view=bribe_view)
                            bribe_view.message = await i.original_response()
                        elif i:
                            msg = await i.followup.edit_message(i.message.id, embed=res_embed, view=bribe_view)
                            bribe_view.message = msg

            game_type = mission.get("minigame", "guess")
            view = get_minigame_view(game_type, interaction.user.id, potential_reward, on_minigame_complete, context="crime")
            
            if hasattr(view, "desc") and view.desc:
                embed.description += f"\n\n{view.desc}"
            if hasattr(view, "question") and view.question:
                embed.description += f"\n\n**Завдання:** {view.question}"

            await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
            view.message = await interaction.original_response()

        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"<:warning:1485598476850040843> Помилка: `{e}`", ephemeral=True)
            else:
                await interaction.followup.send(f"<:warning:1485598476850040843> Помилка: `{e}`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(CrimeCommand(bot))
