from __future__ import annotations

import time
import datetime
import discord
from discord import app_commands
from discord.ext import commands
from config.constants import Emojis

from modules.db import get_database
from repositories.user import get_user
from commands.economy.quests_data import get_random_quests

db = get_database()

def is_same_day(t1: float, t2: float) -> bool:
    d1 = datetime.datetime.fromtimestamp(t1).date()
    d2 = datetime.datetime.fromtimestamp(t2).date()
    return d1 == d2

def is_same_week(t1: float, t2: float) -> bool:
    d1 = datetime.datetime.fromtimestamp(t1).isocalendar()[:2]
    d2 = datetime.datetime.fromtimestamp(t2).isocalendar()[:2]
    return d1 == d2

async def get_or_roll_quests(guild_id: int, user_id: int, eco: dict) -> dict:
    """Лазіва ініціалізація або оновлення квестів"""
    user_data = await get_user(db, guild_id, user_id)
    user_quests = user_data.get("quests", {})
    
    now = time.time()
    last_daily = user_quests.get("last_daily", 0)
    last_weekly = user_quests.get("last_weekly", 0)
    
    updated = False
    
    if not is_same_day(now, last_daily):
        count = eco.get("quests_daily_count", 3)
        new_daily = get_random_quests("daily", count, eco=eco)
        user_quests["daily"] = [{"id": q["id"], "action": q["action"], "target": q["target"], "desc": q["desc"], "progress": 0, "claimed": False} for q in new_daily]
        user_quests["last_daily"] = now
        updated = True
        
    if not is_same_week(now, last_weekly):
        count = eco.get("quests_weekly_count", 2)
        new_weekly = get_random_quests("weekly", count, eco=eco)
        user_quests["weekly"] = [{"id": q["id"], "action": q["action"], "target": q["target"], "desc": q["desc"], "progress": 0, "claimed": False} for q in new_weekly]
        user_quests["last_weekly"] = now
        updated = True
        
    if updated:
        await db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"quests": user_quests}})
        
    return user_quests

async def quest_hook(guild_id: int, user_id: int, action: str, amount: int = 1):
    """Викликається з інших модулів (work, gambling, duel, etc)"""
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    eco = settings.get("economy", {})
    if not eco.get("enabled", True) or not eco.get("quests_enabled", True):
        return
        
    user_quests = await get_or_roll_quests(guild_id, user_id, eco)
    
    changed = False
    for section in ["daily", "weekly"]:
        for q in user_quests.get(section, []):
            if q["action"] == action and not q["claimed"] and q["progress"] < q["target"]:
                q["progress"] += amount
                if q["progress"] > q["target"]:
                    q["progress"] = q["target"]
                changed = True
                
    if changed:
        await db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"quests": user_quests}})

class QuestsView(discord.ui.View):
    def __init__(self, owner_id: int, eco: dict, quests_obj: dict):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.eco = eco
        self.quests_obj = quests_obj

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("<:close:1485598320935174317> Це не ваші квести!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Отримати нагороди", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str("<:gift:1485614389984755772>"))
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_data = await get_user(db, interaction.guild.id, interaction.user.id)
        user_quests = user_data.get("quests", {})
        
        mult = self.eco.get("quests_target_multiplier", 50)
        total_coins = 0
        claimed_count = 0
        
        for section, rew_key in [("daily", "quests_daily_reward"), ("weekly", "quests_weekly_reward")]:
            base_rew = self.eco.get(rew_key, 200)
            for q in user_quests.get(section, []):
                if q["progress"] >= q["target"] and not q["claimed"]:
                    q["claimed"] = True
                    final_rew = base_rew + (q["target"] * mult)
                    total_coins += final_rew
                    claimed_count += 1
                    
        if claimed_count == 0:
            return await interaction.response.send_message("<:close:1485598320935174317> Немає виконаних квестів для отримання нагороди.", ephemeral=True)
            
        await db.users.update_one(
            {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
            {
                "$inc": {"wallet": total_coins, "total_earned": total_coins},
                "$set": {"quests": user_quests},
                "$push": {"eco_history": {"$each": [{"log": f"{Emojis.PLUS.value} **{total_coins}** | Нагороди за квести ({claimed_count} шт) | <t:{int(time.time())}:t>"}], "$slice": -50}}
            }
        )
        
        self.quests_obj = user_quests
        embed = build_quests_embed(interaction.user, user_quests, self.eco)
        await interaction.response.edit_message(content=f"<:check:1485597845883981905> Нагорода отримана: **{total_coins}** {self.eco.get('currency_emoji', '<:coin:1485610808003133552>')}", embed=embed, view=self)

def build_progress_bar(progress: int, target: int, length: int = 10) -> str:
    if target <= 0: return "█" * length
    filled = max(0, min(length, round((progress / target) * length)))
    return "█" * filled + "░" * (length - filled)

def build_quests_embed(user: discord.Member, quests_obj: dict, eco: dict) -> discord.Embed:
    curr = eco.get("currency_emoji", "<:coin:1485610808003133552>")
    embed = discord.Embed(
        title=f"<:menuandlist:1485605053246083143> Завдання {user.display_name}", 
        color=0x000000
    )
    
    mult = eco.get("quests_target_multiplier", 50)
    
    def get_emoji(action: str) -> str:
        if action in ["crime", "economy.rob"]: 
            return "<:mask:1485625427014713394>"
        return "<:flame:1485618663489929356>"

    for section, rew_key, title_emoji, title in [
        ("daily", "quests_daily_reward", "<:clock:1485618008784113796>", "Денні завдання"), 
        ("weekly", "quests_weekly_reward", "<:day7:1485604215496900639>", "Тижневі завдання")
    ]:
        base_rew = eco.get(rew_key, 200)
        qs = quests_obj.get(section, [])
        lines = []
        for q in qs:
            perc = int((q["progress"] / q["target"]) * 100) if q["target"] > 0 else 100
            perc = min(100, perc)
            final_rew = base_rew + (q["target"] * mult)
            pbar = build_progress_bar(q["progress"], q["target"])
            e_icon = get_emoji(q["action"])
            
            if q["claimed"]:
                lines.append(f"<:check:1485597845883981905> ~~**{q['desc']}**~~\n{q['progress']}/{q['target']} (100%) • `+{final_rew}` {curr}\n{pbar}")
            else:
                lines.append(f"{e_icon} **{q['desc']}**\n{q['progress']}/{q['target']} ({perc}%) • `+{final_rew}` {curr}\n{pbar}")
                
        if not lines:
            lines.append("Немає завдань.")
            
        embed.add_field(name=f"{title_emoji} {title}", value="\n\n".join(lines), inline=False)
        
    embed.set_footer(text="Виконуй квести під час гри та тисни 'Отримати нагороди'")
    return embed

class QuestsCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="quests", description="Переглянути та виконати квести")
    async def quests(self, interaction: discord.Interaction):
        settings = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        eco = settings.get("economy", {})
        if not eco.get("enabled", True) or not eco.get("quests_enabled", True):
            return await interaction.response.send_message("<:close:1485598320935174317> Квести або економіка вимкнені.", ephemeral=True)
            
        quests_obj = await get_or_roll_quests(interaction.guild.id, interaction.user.id, eco)
        embed = build_quests_embed(interaction.user, quests_obj, eco)
        view = QuestsView(interaction.user.id, eco, quests_obj)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(QuestsCommand(bot))
