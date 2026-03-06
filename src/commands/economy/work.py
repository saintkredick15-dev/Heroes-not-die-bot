"""
/work — Робота з системою подій та КНП міні-грою.
- Легка робота: базовий результат + 40% шанс на подію (КНП або монетка)
- Складна робота: вибір стратегії → успіх/провал
"""
from __future__ import annotations

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import time
import random

from modules.db import get_database
from repositories.user import get_user
from commands.economy.events import (
    JOBS_SIMPLE, JOBS_COMPLEX, SIMPLE_EVENTS,
    SIMPLE_SCENES, COMPLEX_SCENES, MathView
)
from commands.economy.quests import quest_hook
from commands.economy.minigames import get_random_minigame
from commands.economy.crime import get_minigame_view  
from utils.eco_helpers import make_log

db = get_database()

# ── Емодзі ────────────────────────────────────────────────────────────────────
E_CHECK = "<:cutiecheckmark:1479120440734650389>"
E_CROSS = "<:krestik:1476693091355463842>"
E_WORK  = "<:work:1478489752020975626>"
E_WORKS = "<:works:1478510456971857992>"
E_COIN  = "<:coin:1478487028105482485>"
E_CLOCK = "<:clock:1476209087804084328>"
E_FLAME = "<:flame:1478490474145906800>"
E_LEFT  = "<:totheleft:1478825190749110323>"

EMBED_COLOR_WIN  = 0x000000   
EMBED_COLOR_LOSE = 0x000000
EMBED_COLOR_BASE = 0x000000
EMBED_COLOR_WORK = 0x000000

RPS_CHOICES   = ["Камінь", "Ножиці", "Папір"]
RPS_EMOJI     = {"Камінь": "🪨", "Ножиці": "✂️", "Папір": "📄"}
RPS_BEATS     = {"Камінь": "Ножиці", "Ножиці": "Папір", "Папір": "Камінь"}

def add_history(amount: int, desc: str) -> dict:
    now = int(time.time())
    color = "🟢" if amount >= 0 else "🔴"
    val = abs(amount)
    return {"log": f"{color} **{val}** | {desc} | <t:{now}:t>"}

def get_full_eco(settings: dict) -> dict:
    from commands.administration.economy_setup import DEFAULT_ECO, get_eco
    return get_eco(settings)

# ── Вибір типу роботи ───────────────────────────────────────────────────────────

class WorkTypeView(discord.ui.View):
    def __init__(self, user_id: int, eco: dict, user_data: dict, cog: 'WorkCommand'):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.eco = eco
        self.user_data = user_data
        self.cog = cog

    @discord.ui.button(label="Легка Робота", emoji="🧹", style=discord.ButtonStyle.success)
    async def btn_simple(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(f"{E_CROSS} Це не твоє меню!", ephemeral=True)
        await interaction.response.defer()
        await self.cog.execute_simple(interaction, self.eco, self.user_data)
        self.stop()
        
    @discord.ui.button(label="Складна Робота", emoji="🕵️", style=discord.ButtonStyle.danger)
    async def btn_complex(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(f"{E_CROSS} Це не твоє меню!", ephemeral=True)
        await interaction.response.defer()
        await self.cog.execute_complex(interaction, self.eco, self.user_data)
        self.stop()

# ── Логіка команди ────────────────────────────────────────────────────────────

class WorkCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def execute_simple(self, interaction: discord.Interaction, eco: dict, user_data: dict):
        work_min = eco.get("work_min", 100)
        work_max = eco.get("work_max", 500)
        curr     = eco.get("currency_emoji", E_COIN)

        earned   = random.randint(work_min, work_max)
        
        job = random.choice(JOBS_SIMPLE)

        embed = discord.Embed(
            title=f"{E_WORK} Зміна завершена!",
            description=job["desc"].format(amount=earned, curr=curr),
            color=EMBED_COLOR_WIN
        )

        event_chance = eco.get("event_chance", 40)
        triggered    = random.randint(1, 100) <= event_chance

        if not triggered:
            
            now = int(time.time())
            boost_active = now < user_data.get("coin_boost_until", 0)
            if boost_active:
                earned = earned * 2

            await db.users.update_one(
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                {
                    "$inc": {"wallet": earned, "total_earned": earned},
                    "$set": {"work_last": int(time.time())},
                    "$push": {"eco_history": {"$each": [make_log(earned, "Легка робота")], "$slice": -50}}
                }
            )
            await quest_hook(interaction.guild.id, interaction.user.id, "work")
            embed.set_footer(text=f"Зараховано {earned} {eco.get('currency_name', 'монет')}" + (" 🌟 x2 Boost" if boost_active else ""))
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        scene = random.choice(SIMPLE_SCENES)
        game_type = scene.get("minigame", "coinflip")
        reward_mult = scene.get("reward_mult", 1.3)
        fail_penalty = scene.get("fail_penalty", 0.1)

        event_embed = discord.Embed(
            title=f"🛑 {scene['title']}",
            description=(
                f"{job['desc'].format(amount=earned, curr=curr)}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"**Несподіванка!** {scene['desc']}\n"
            ),
            color=0xffa500
        )
        
        event_embed.set_footer(text="Подумай швидко!")

        async def on_minigame_complete(i: discord.Interaction | None, outcome: str, res_embed: discord.Embed, game_view: discord.ui.View):
            now = int(time.time())
            if outcome == "win":
                final_earned = int(earned * reward_mult)
                boost_active = now < user_data.get("coin_boost_until", 0)
                if boost_active:
                    final_earned = final_earned * 2

                res_embed.title = "✅ Ти впорався з ситуацією!"
                res_embed.description = f"{res_embed.description}\n\nБазовий заробіток збільшено! Зараховано: **{final_earned:,}** {curr}"
                res_embed.color = EMBED_COLOR_WIN
            elif outcome == "draw":
                final_earned = earned
                res_embed.title = "🤝 Нічия / Відміна"
                res_embed.description = f"{res_embed.description}\n\nТи залишаєшся при своєму. Зараховано: **{final_earned:,}** {curr}"
                res_embed.color = 0xffff00
            else:
                penalty = int(earned * fail_penalty)
                final_earned = max(0, earned - penalty)
                res_embed.title = "❌ Невдача!"
                res_embed.description = f"{res_embed.description}\n\nЧастина заробітку втрачена. Зараховано: **{final_earned:,}** {curr}"
                res_embed.color = EMBED_COLOR_LOSE

            await db.users.update_one(
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                {
                    "$inc": {"wallet": final_earned, "total_earned": final_earned},
                    "$set": {"work_last": now},
                    "$push": {"eco_history": {"$each": [make_log(final_earned, f"Робота: {scene['title']}")], "$slice": -50}}
                }
            )
            await quest_hook(interaction.guild.id, interaction.user.id, "work")

            if i is None:
                try:
                    await interaction.edit_original_response(embed=res_embed, view=game_view)
                except Exception:
                    pass
            elif i.response.is_done():
                await i.edit_original_response(embed=res_embed, view=game_view)
            else:
                await i.response.edit_message(embed=res_embed, view=game_view)

        view = get_minigame_view(game_type, interaction.user.id, 0, on_minigame_complete)
        
        if hasattr(view, "desc") and view.desc:
            event_embed.description += f"\n\n{view.desc}"
        if hasattr(view, "question") and view.question:
            event_embed.description += f"\n\n**Завдання:** {view.question}"

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=event_embed, view=view)
        else:
            await interaction.response.send_message(embed=event_embed, view=view, ephemeral=True)
            
        try:
            view.message = await interaction.original_response()
        except:
            pass

    async def execute_complex(self, interaction: discord.Interaction, eco: dict, user_data: dict):
        """
        Нарративна складна робота: N послідовних сцен з однієї сюжетної лінії.
        """
        mission    = random.choice(JOBS_COMPLEX)
        curr       = eco.get("currency_emoji", E_COIN)
        work_max   = eco.get("work_max", 500)
        n_stages   = max(1, min(5, eco.get("work_complex_stages", 3)))
        base_pay   = random.randint(work_max * 2, work_max * 4)

        from commands.economy.events import COMPLEX_SCENES
        storyline_name = random.choice(list(COMPLEX_SCENES.keys()))
        full_storyline = COMPLEX_SCENES[storyline_name]
        
        scenes = full_storyline[:n_stages]

        await db.users.update_one(
            {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
            {"$set": {"work_started_at": int(time.time())}}
        )

        state = {
            "mission": mission,
            "scenes": scenes,
            "current_scene": 0,
            "base_pay": base_pay,
            "accumulated": base_pay,
        }

        await self._run_scene(interaction, eco, user_data, state, first_response=True)

    async def _run_scene(self, interaction: discord.Interaction, eco: dict, user_data: dict, state: dict, first_response: bool = False):
        """Run the current scene of a complex mission."""
        idx     = state["current_scene"]
        scenes  = state["scenes"]
        mission = state["mission"]
        curr    = eco.get("currency_emoji", E_COIN)

        if idx >= len(scenes):
            
            return await self._end_complex(interaction, eco, user_data, state)

        scene = scenes[idx]
        total_scenes = len(scenes)

        embed = discord.Embed(
            title=f"👷‍♂️ {mission['title']} • Етап {idx+1}/{total_scenes}",
            description=(
                f"{scene['desc']}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💰 Поточна виплата: **{state['accumulated']:,}** {curr}\n"
                f"✅ Успіх → ×{scene['reward_mult']} | ❌ Поразка → -{int(scene['fail_penalty']*100)}%"
            ),
            color=EMBED_COLOR_WORK
        )
        embed.set_footer(text="Уважно проходь кожен етап!")
        
        game_type = scene.get("minigame", "coinflip")

        async def scene_callback(i: discord.Interaction | None, outcome: str, res_embed: discord.Embed, game_view: discord.ui.View):
            won = outcome == "win"
            if won:
                state["accumulated"] = int(state["accumulated"] * scene["reward_mult"])
            elif outcome == "lose":
                state["accumulated"] = max(0, int(state["accumulated"] * (1 - scene["fail_penalty"])))
            
            state["current_scene"] += 1
            
            res_embed.description = f"{res_embed.description}\n\nОновлений баланс місії: **{state['accumulated']:,}** {curr}"
            
            if i is None:
                try:
                    await interaction.edit_original_response(embed=res_embed, view=None)
                except:
                    pass
            elif i.response.is_done():
                await i.edit_original_response(embed=res_embed, view=None)
            else:
                await i.response.edit_message(embed=res_embed, view=None)
                
            await asyncio.sleep(2)  
            
            next_interaction = i if i and not (i is None) else interaction
            await self._run_scene(next_interaction, eco, user_data, state, first_response=False)

        view = get_minigame_view(game_type, interaction.user.id, 0, scene_callback)
        
        if hasattr(view, "desc") and view.desc:
            embed.description += f"\n\n{view.desc}"
        if hasattr(view, "question") and view.question:
            embed.description += f"\n\n**Завдання:** {view.question}"

        if first_response:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            try:
                view.message = await interaction.original_response()
            except:
                pass
        else:
            try:
                if interaction.response.is_done():
                    await interaction.edit_original_response(embed=embed, view=view)
                else:
                    await interaction.response.edit_message(embed=embed, view=view)
            except Exception:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                
            try:
                view.message = await interaction.original_response()
            except:
                pass

    async def _end_complex(self, interaction: discord.Interaction, eco: dict, user_data: dict, state: dict):
        """Finalize complex work and pay out."""
        final_pay = state["accumulated"]
        curr      = eco.get("currency_emoji", E_COIN)
        mission   = state["mission"]
        now       = int(time.time())

        await db.users.update_one(
            {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
            {
                "$inc": {"wallet": final_pay, "total_earned": final_pay, "week_earned": final_pay, "month_earned": final_pay},
                "$set": {"work_last": now, "work_started_at": 0},
                "$push": {"eco_history": {
                    "$each": [{"log": f"🟢 **{final_pay}** | Складна робота: {mission['title']} | <t:{now}:t>"}],
                    "$slice": -50
                }}
            }
        )
        await quest_hook(interaction.guild.id, interaction.user.id, "work")

        done_embed = discord.Embed(
            title=f"✅ Місія завершена!",
            description=(
                f"👷‍♂️ **{mission['title']}** — всі {len(state['scenes'])} етапи пройдено.\n\n"
                f"💰 Підсумок: **+{final_pay:,}** {curr}"
            ),
            color=EMBED_COLOR_WIN
        )
        try:
            await interaction.edit_original_response(embed=done_embed, view=None)
        except Exception:
            await interaction.followup.send(embed=done_embed, ephemeral=True)

    @app_commands.command(name="work", description="Працювати та заробляти валюту")
    async def work(self, interaction: discord.Interaction):
        try:
            settings  = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
            eco       = settings.get("economy", {})

            from commands.administration.economy_setup import DEFAULT_ECO, get_eco
            eco = get_eco(settings)

            if not eco.get("enabled", True):
                await interaction.response.send_message("❌ Економіка вимкнена на цьому сервері.", ephemeral=True)
                return

            user_data = await get_user(db, interaction.guild.id, interaction.user.id)
            now       = int(time.time())
            last_work = user_data.get("work_last", 0)
            cooldown  = eco.get("work_cooldown", 14400)

            crime_ban = user_data.get("crime_ban_until", 0)
            if crime_ban and now < crime_ban:
                remaining = crime_ban - now
                m, s = divmod(remaining, 60)
                h, m = divmod(m, 60)
                time_str = f"{h}г {m}хв" if h else f"{m}хв {s}с"
                await interaction.response.send_message(
                    f"⛔ Ти під слідством після провалу крайму. Звільняєшся через **{time_str}**.",
                    ephemeral=True
                )
                return

            work_started = user_data.get("work_started_at", 0)
            if work_started and (now - work_started) < 600:  
                await interaction.response.send_message(
                    f"{E_CLOCK} Ти ще на завданні! Завершуй поточну роботу.",
                    ephemeral=True
                )
                return

            if last_work and (now - last_work) < cooldown:
                remaining = int(cooldown - (now - last_work))
                m, s = divmod(remaining, 60)
                h, m = divmod(m, 60)
                time_str = f"{h}г {m}хв" if h else f"{m}хв {s}с"
                await interaction.response.send_message(
                    f"{E_CLOCK} Ти втомився після зміни! Повертайся через **{time_str}**.",
                    ephemeral=True
                )
                return

            work_type = eco.get("work_type", "both")

            if work_type == "both":
                curr = eco.get("currency_emoji", E_COIN)
                work_min = eco.get("work_min", 100)
                work_max = eco.get("work_max", 500)
                embed = discord.Embed(
                    title="👷 Біржа праці",
                    description=(
                        "Обери тип роботи на сьогодні.\n\n"
                        f"🧹 **Легка** — `{work_min}–{work_max}` {curr}, **100% успіх** + шанс на подію\n"
                        f"🕵️ **Складна** — `{work_max*2}–{work_max*4}` {curr}, **ризик провалу** + вибір стратегії"
                    ),
                    color=EMBED_COLOR_WORK
                )
                view = WorkTypeView(interaction.user.id, eco, user_data, self)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            elif work_type == "complex":
                await interaction.response.defer()
                await self.execute_complex(interaction, eco, user_data)
            else:
                await interaction.response.defer()
                await self.execute_simple(interaction, eco, user_data)

        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"⚠️ Помилка: `{e}`", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠️ Помилка: `{e}`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(WorkCommand(bot))
