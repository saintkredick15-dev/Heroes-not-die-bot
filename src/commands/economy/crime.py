"""
/crime — Ризикована операція. Вищий дохід, штраф-бан при провалі.
"""
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
from utils.eco_helpers import make_log
from commands.economy.minigames import (
    MathQuizView, HigherLowerView, ShellGameView, DiceDuelView,
    OddEmojiView, UnscrambleView, TriviaView, TypingTestView,
    GuessNumberView, ReactionTestView
)
from commands.economy.events import CRIMES
from commands.economy.quests import quest_hook
from utils.eco_helpers import make_log

db = get_database()

E_COIN    = "<:coin:1478487028105482485>"
E_CROSS   = "<:krestik:1476693091355463842>"
E_CHECK   = "<:cutiecheckmark:1479120440734650389>"
E_ROBBERY = "<:robbery:1478496325887725814>"
E_CLOCK   = "<:clock:1476209087804084328>"
COLOR_WIN  = 0x57f287
COLOR_LOSE = 0xed4245
COLOR_BASE = 0x1a1a2e

def fmt_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h and m: return f"{h}г {m}хв"
    if h: return f"{h}г"
    return f"{m}хв"

def get_minigame_view(game_type: str, owner_id: int, stake: int, on_complete):
    """Повертає View (або Modal) відповідної міні-гри"""
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
    return game_class(owner_id, stake, on_complete)

class CrimeCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crime", description="Ризикована кримінальна операція")
    async def crime(self, interaction: discord.Interaction):
        try:
            settings  = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
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
                    f"⏳ Наступна операція доступна через **{fmt_duration(remaining)}**.",
                    ephemeral=True
                )
                return

            mission    = random.choice(CRIMES)
            curr       = eco.get("currency_emoji", E_COIN)
            work_max   = eco.get("work_max", 500)
            
            potential_reward = int(random.randint(int(work_max * 3), int(work_max * 6)))

            embed = discord.Embed(
                title=f"🚨 {mission['title']}",
                description=mission['desc'],
                color=0x1a1a2e
            )
            embed.set_footer(text="Починаємо операцію... готуйся!")

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
                    
                    res_embed.title = "✅ Операція пройшла успішно!"
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
                    ban_until  = int(time.time()) + ban_dur

                    await db.users.update_one(
                        {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                        {
                            "$inc": {"wallet": -fine},
                            "$set": {"crime_last": int(time.time()), "crime_ban_until": ban_until},
                            "$push": {"eco_history": {"$each": [make_log(-fine, f"Провал крайму: {mission['title']}")], "$slice": -50}}
                        }
                    )
                    res_embed.title = "🚨 Провал операції!"
                    res_embed.description = (f"{res_embed.description}\n\n{E_CROSS} Знято штраф: **{fine:,}** {curr}\n"
                                             f"Ти під слідством на **{fmt_duration(ban_dur)}** — всі eco-команди заблоковані.")
                    res_embed.color = COLOR_LOSE

                if getattr(game_view, "message", None):
                    await game_view.message.edit(embed=res_embed, view=game_view)
                elif i and not i.response.is_done():
                    await i.response.edit_message(embed=res_embed, view=game_view)
                elif i:
                    await i.followup.edit_message(i.message.id, embed=res_embed, view=game_view)

            game_type = mission.get("minigame", "guess")
            view = get_minigame_view(game_type, interaction.user.id, potential_reward, on_minigame_complete)
            
            if hasattr(view, "desc") and view.desc:
                embed.description += f"\n\n{view.desc}"
            if hasattr(view, "question") and view.question:
                embed.description += f"\n\n**Завдання:** {view.question}"

            await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
            view.message = await interaction.original_response()

        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"⚠️ Помилка: `{e}`", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠️ Помилка: `{e}`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(CrimeCommand(bot))
