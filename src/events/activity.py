import discord
from discord.ext import commands, tasks
from datetime import datetime
from src.modules.db import get_database

db = get_database()

async def get_user_data(guild_id, user_id):
    user = await db.users.find_one({"guild_id": guild_id, "user_id": user_id})
    if not user:
        user = {
            "guild_id": guild_id,
            "user_id": user_id,
            "xp": 0,
            "level": 1,
            "messages": 0,
            "voice_minutes": 0,
            "reactions": 0,
            "history": {}
        }
        await db.users.insert_one(user)
    return user

async def update_user_data(guild_id, user: discord.Member, update_data):
    # Додаємо збереження імені та аватару для сайту
    update_data["username"] = user.display_name
    update_data["avatar"] = user.display_avatar.url if user.display_avatar else None
    
    await db.users.update_one(
        {"guild_id": guild_id, "user_id": user.id},
        {"$set": update_data}
    )

def get_level_xp(level):
    return 5 * (level ** 2) + 50 * level + 100

async def level_up_check(message, user_data):
    needed_xp = get_level_xp(user_data["level"])
    if user_data["xp"] >= needed_xp:
        user_data["xp"] -= needed_xp
        user_data["level"] += 1
        
        # Передаємо об'єкт member, а не просто ID
        await update_user_data(message.guild.id, message.author, {
            "xp": user_data["xp"],
            "level": user_data["level"]
        })

class ActivityEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_voice_time.start()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        user_data = await get_user_data(message.guild.id, message.author.id)
        
        today = datetime.now().strftime("%Y-%m-%d")
        history = user_data.get("history", {})
        history[today] = history.get(today, 0) + 10
        
        update_data = {
            "xp": user_data["xp"] + 10,
            "messages": user_data["messages"] + 1,
            "history": history
        }
        
        user_data.update(update_data)
        await update_user_data(message.guild.id, message.author, update_data)
        await level_up_check(message, user_data)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return
        
        user_data = await get_user_data(reaction.message.guild.id, user.id)
        
        today = datetime.now().strftime("%Y-%m-%d")
        history = user_data.get("history", {})
        history[today] = history.get(today, 0) + 2
        
        update_data = {
            "xp": user_data["xp"] + 2,
            "reactions": user_data["reactions"] + 1,
            "history": history
        }
        
        await update_user_data(reaction.message.guild.id, user, update_data)

    @tasks.loop(minutes=1)
    async def update_voice_time(self):
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        user_data = await get_user_data(guild.id, member.id)
                        
                        today = datetime.now().strftime("%Y-%m-%d")
                        history = user_data.get("history", {})
                        history[today] = history.get(today, 0) + 5
                        
                        update_data = {
                            "xp": user_data["xp"] + 5,
                            "voice_minutes": user_data["voice_minutes"] + 1,
                            "history": history
                        }
                        
                        await update_user_data(guild.id, member, update_data)

async def setup(bot):
    await bot.add_cog(ActivityEvents(bot))