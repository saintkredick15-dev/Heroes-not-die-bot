from __future__ import annotations

import asyncio
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from commands.economy.crime import get_minigame_view
from commands.economy.events import COMPLEX_SCENES, JOBS_COMPLEX, JOBS_SIMPLE, SIMPLE_SCENES
from commands.economy.quests import quest_hook
from config.constants import Emojis as _E
from modules.db import get_database
from repositories.user import get_user
from utils.eco_helpers import apply_inflation, make_log
from utils.ui_contract import add_section, gameplay_result_embed, set_surface_footer, surface_embed

db = get_database()

E_CHECK = _E.CHECK.value
E_CROSS = _E.CROSS.value
E_WORK = _E.WORK.value
E_COIN = _E.COIN.value
E_CLOCK = _E.CLOCK.value


class WorkTypeView(discord.ui.View):
    def __init__(self, user_id: int, eco: dict, user_data: dict, cog: "WorkCommand"):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.eco = eco
        self.user_data = user_data
        self.cog = cog

    @discord.ui.button(label="Легка робота", emoji="🧹", style=discord.ButtonStyle.success)
    async def btn_simple(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(f"{E_CROSS} Це не твоє меню!", ephemeral=True)
        await interaction.response.defer()
        await self.cog.execute_simple(interaction, self.eco, self.user_data)
        self.stop()

    @discord.ui.button(label="Складна робота", emoji="🕵️", style=discord.ButtonStyle.danger)
    async def btn_complex(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(f"{E_CROSS} Це не твоє меню!", ephemeral=True)
        await interaction.response.defer()
        await self.cog.execute_complex(interaction, self.eco, self.user_data)
        self.stop()


class WorkCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def execute_simple(self, interaction: discord.Interaction, eco: dict, user_data: dict):
        work_min = eco.get("work_min", 100)
        work_max = eco.get("work_max", 500)
        curr = eco.get("currency_emoji", E_COIN)

        earned = random.randint(work_min, work_max)
        from utils.eco_helpers import calculate_tax

        wallet = user_data.get("wallet", 0)
        bank = user_data.get("bank", 0)
        final_earned, tax, tax_pct_str = calculate_tax(earned, wallet, bank)
        job = random.choice(JOBS_SIMPLE)

        earned_text = f"**{final_earned}** {curr}"
        if tax > 0:
            earned_text += f"\n*(Стягнуто податок на багатство {tax_pct_str}: -{tax} {curr})*"

        embed = surface_embed(
            "gameplay",
            f"{E_WORK} Зміна завершена",
            job["desc"].format(amount=earned_text, curr=""),
            tone="success",
        )

        event_chance = eco.get("event_chance", 40)
        triggered = random.randint(1, 100) <= event_chance

        if not triggered:
            now = int(time.time())
            boost_active = now < user_data.get("coin_boost_until", 0)
            if boost_active:
                final_earned *= 2

            await db.users.update_one(
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                {
                    "$inc": {"wallet": final_earned, "total_earned": final_earned},
                    "$set": {"work_last": int(time.time())},
                    "$push": {"eco_history": {"$each": [make_log(final_earned, "Легка робота")], "$slice": -50}},
                },
            )
            from modules.db import invalidate_user_data

            await invalidate_user_data(interaction.guild.id, interaction.user.id)
            await quest_hook(interaction.guild.id, interaction.user.id, "work")
            await apply_inflation(db, interaction.guild.id, final_earned, eco)
            set_surface_footer(
                embed,
                "gameplay",
                f"Зараховано {final_earned} {eco.get('currency_name', 'монет')}" + (" • x2 Boost" if boost_active else ""),
            )
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        scene = random.choice(SIMPLE_SCENES)
        game_type = scene.get("minigame", "coinflip")
        reward_mult = scene.get("reward_mult", 1.3)
        fail_penalty = scene.get("fail_penalty", 0.1)

        event_embed = surface_embed(
            "gameplay",
            f"🛑 {scene['title']}",
            f"{job['desc'].format(amount=earned_text, curr='')}\n\n**Несподіванка!** {scene['desc']}",
            tone="warning",
        )
        set_surface_footer(event_embed, "gameplay", "Подумай швидко й закрий подію правильно.")

        async def on_minigame_complete(i: discord.Interaction | None, outcome: str, res_embed: discord.Embed, game_view: discord.ui.View):
            now = int(time.time())
            if outcome == "win":
                final_earned = int(earned * reward_mult)
                boost_active = now < user_data.get("coin_boost_until", 0)
                if boost_active:
                    final_earned *= 2
                res_embed.title = "Ти впорався з ситуацією"
                res_embed.description = (
                    f"{res_embed.description}\n\nБазовий заробіток збільшено. "
                    f"Зараховано: **{final_earned:,}** {curr}"
                )
                res_embed.color = gameplay_result_embed("tmp", "", tone="success").color
            elif outcome == "draw":
                final_earned = earned
                res_embed.title = "Нічия / Відміна"
                res_embed.description = (
                    f"{res_embed.description}\n\nТи лишаєшся при своєму. "
                    f"Зараховано: **{final_earned:,}** {curr}"
                )
                res_embed.color = gameplay_result_embed("tmp", "", tone="warning").color
            else:
                penalty = int(earned * fail_penalty)
                final_earned = max(0, earned - penalty)
                res_embed.title = "Невдача"
                res_embed.description = (
                    f"{res_embed.description}\n\nЧастину заробітку втрачено. "
                    f"Зараховано: **{final_earned:,}** {curr}"
                )
                res_embed.color = gameplay_result_embed("tmp", "", tone="error").color

            await db.users.update_one(
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
                {
                    "$inc": {"wallet": final_earned, "total_earned": final_earned},
                    "$set": {"work_last": now},
                    "$push": {"eco_history": {"$each": [make_log(final_earned, f"Робота: {scene['title']}")], "$slice": -50}},
                },
            )
            await quest_hook(interaction.guild.id, interaction.user.id, "work")
            if outcome in {"win", "draw"}:
                await apply_inflation(db, interaction.guild.id, final_earned, eco)

            set_surface_footer(res_embed, "gameplay", f"Підсумок зміни • {final_earned:,} {curr}")

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
        except Exception:
            pass

    async def execute_complex(self, interaction: discord.Interaction, eco: dict, user_data: dict):
        mission = random.choice(JOBS_COMPLEX)
        work_max = eco.get("work_max", 500)
        n_stages = max(1, min(5, eco.get("work_complex_stages", 3)))
        base_pay = random.randint(work_max * 2, work_max * 4)

        storyline_name = random.choice(list(COMPLEX_SCENES.keys()))
        full_storyline = COMPLEX_SCENES[storyline_name]
        scenes = full_storyline[:n_stages]

        await db.users.update_one(
            {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
            {"$set": {"work_started_at": int(time.time())}},
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
        idx = state["current_scene"]
        scenes = state["scenes"]
        mission = state["mission"]
        curr = eco.get("currency_emoji", E_COIN)

        if idx >= len(scenes):
            return await self._end_complex(interaction, eco, user_data, state)

        scene = scenes[idx]
        total_scenes = len(scenes)
        embed = surface_embed(
            "gameplay",
            f"👷‍♂️ {mission['title']} • Етап {idx + 1}/{total_scenes}",
            scene["desc"],
            tone="warning",
        )
        add_section(
            embed,
            "Умови етапу",
            [
                f"Поточна виплата: **{state['accumulated']:,}** {curr}",
                f"Успіх → x{scene['reward_mult']}",
                f"Поразка → -{int(scene['fail_penalty'] * 100)}%",
            ],
        )
        set_surface_footer(embed, "gameplay", "Пройди етап і втримай баланс місії.")

        game_type = scene.get("minigame", "coinflip")

        async def scene_callback(i: discord.Interaction | None, outcome: str, res_embed: discord.Embed, game_view: discord.ui.View):
            if outcome == "win":
                state["accumulated"] = int(state["accumulated"] * scene["reward_mult"])
            elif outcome == "lose":
                state["accumulated"] = max(0, int(state["accumulated"] * (1 - scene["fail_penalty"])))

            state["current_scene"] += 1
            res_embed.description = f"{res_embed.description}\n\nОновлений баланс місії: **{state['accumulated']:,}** {curr}"
            set_surface_footer(res_embed, "gameplay", f"Поточний баланс місії • {state['accumulated']:,} {curr}")

            if i is None:
                try:
                    await interaction.edit_original_response(embed=res_embed, view=None)
                except Exception:
                    pass
            elif i.response.is_done():
                await i.edit_original_response(embed=res_embed, view=None)
            else:
                await i.response.edit_message(embed=res_embed, view=None)

            await asyncio.sleep(2)
            next_interaction = i if i is not None else interaction
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
            except Exception:
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
            except Exception:
                pass

    async def _end_complex(self, interaction: discord.Interaction, eco: dict, user_data: dict, state: dict):
        final_pay = state["accumulated"]
        from utils.eco_helpers import calculate_tax

        wallet = user_data.get("wallet", 0)
        bank = user_data.get("bank", 0)
        final_earned, tax, tax_pct_str = calculate_tax(final_pay, wallet, bank)

        curr = eco.get("currency_emoji", E_COIN)
        mission = state["mission"]
        now = int(time.time())

        await db.users.update_one(
            {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
            {
                "$inc": {
                    "wallet": final_earned,
                    "total_earned": final_earned,
                    "week_earned": final_earned,
                    "month_earned": final_earned,
                },
                "$set": {"work_last": now, "work_started_at": 0},
                "$push": {
                    "eco_history": {
                        "$each": [{"log": f"🟢 **{final_earned}** | Складна робота: {mission['title']} | <t:{now}:t>"}],
                        "$slice": -50,
                    }
                },
            },
        )
        from modules.db import invalidate_user_data

        await invalidate_user_data(interaction.guild.id, interaction.user.id)
        await quest_hook(interaction.guild.id, interaction.user.id, "work")
        await apply_inflation(db, interaction.guild.id, final_pay, eco)

        earned_text = f"**+{final_earned:,}** {curr}"
        if tax > 0:
            earned_text += f"\n*(Стягнуто податок на багатство {tax_pct_str}: -{tax:,} {curr})*"

        done_embed = gameplay_result_embed(
            "Місія завершена",
            f"**{mission['title']}** — усі {len(state['scenes'])} етапи пройдено.\n\nПідсумок: {earned_text}",
            tone="success",
        )
        try:
            await interaction.edit_original_response(embed=done_embed, view=None)
        except Exception:
            await interaction.followup.send(embed=done_embed, ephemeral=True)

    @app_commands.command(name="work", description="Працювати та заробляти валюту")
    async def work(self, interaction: discord.Interaction):
        try:
            from commands.administration.economy_setup import get_eco
            from utils.eco_helpers import check_account_age
            from modules.db import get_guild_settings

            settings = await get_guild_settings(db, interaction.guild.id)
            eco = get_eco(settings)

            if not eco.get("enabled", True):
                await interaction.response.send_message("<:cutiex:1480246146076119132> Економіка вимкнена на цьому сервері.", ephemeral=True)
                return

            if not await check_account_age(interaction, eco):
                return

            user_data = await get_user(db, interaction.guild.id, interaction.user.id)
            now = int(time.time())
            last_work = user_data.get("work_last", 0)
            cooldown = eco.get("work_cooldown", 14400)

            crime_ban = user_data.get("crime_ban_until", 0)
            if crime_ban and now < crime_ban:
                remaining = crime_ban - now
                m, s = divmod(remaining, 60)
                h, m = divmod(m, 60)
                time_str = f"{h}г {m}хв" if h else f"{m}хв {s}с"
                await interaction.response.send_message(
                    f"⛔ Ти під слідством після провалу крайму. Звільняєшся через **{time_str}**.",
                    ephemeral=True,
                )
                return

            work_started = user_data.get("work_started_at", 0)
            if work_started and (now - work_started) < 600:
                await interaction.response.send_message(
                    f"{E_CLOCK} Ти ще на завданні! Заверши поточну роботу.",
                    ephemeral=True,
                )
                return

            if last_work and (now - last_work) < cooldown:
                remaining = int(cooldown - (now - last_work))
                m, s = divmod(remaining, 60)
                h, m = divmod(m, 60)
                time_str = f"{h}г {m}хв" if h else f"{m}хв {s}с"
                await interaction.response.send_message(
                    f"{E_CLOCK} Ти втомився після зміни! Повертайся через **{time_str}**.",
                    ephemeral=True,
                )
                return

            work_type = eco.get("work_type", "both")

            if work_type == "both":
                curr = eco.get("currency_emoji", E_COIN)
                work_min = eco.get("work_min", 100)
                work_max = eco.get("work_max", 500)
                embed = surface_embed(
                    "gameplay",
                    "👷 Біржа праці",
                    "Обери тип роботи на поточну зміну.",
                    tone="default",
                )
                add_section(
                    embed,
                    "Варіанти",
                    [
                        f"🧹 Легка — `{work_min}–{work_max}` {curr}, 100% успіх + шанс на подію",
                        f"🕵️ Складна — `{work_max * 2}–{work_max * 4}` {curr}, ризик провалу + вибір стратегії",
                    ],
                )
                set_surface_footer(embed, "gameplay", "Швидкий вибір • легка стабільніша, складна прибутковіша.")
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
                await interaction.response.send_message(f"<:warn:1477376152191373504> Помилка: `{e}`", ephemeral=True)
            else:
                await interaction.followup.send(f"<:warn:1477376152191373504> Помилка: `{e}`", ephemeral=True)


async def setup(bot):
    await bot.add_cog(WorkCommand(bot))
