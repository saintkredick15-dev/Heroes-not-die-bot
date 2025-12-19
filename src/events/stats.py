import discord
from discord.ext import commands, tasks
from src.modules.db import get_database

db = get_database()

class BotStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Запускаємо таймер при старті
        self.update_stats.start()

    def cog_unload(self):
        self.update_stats.cancel()

    @tasks.loop(minutes=5.0)  # Оновлюємо кожні 5 хвилин
    async def update_stats(self):
        # Чекаємо, поки бот повністю завантажиться
        await self.bot.wait_until_ready()
        
        # Рахуємо
        server_count = len(self.bot.guilds)
        member_count = sum(guild.member_count for guild in self.bot.guilds)
        
        # Пишемо в базу (в колекцію 'site_stats')
        await db.site_stats.update_one(
            {"_id": "general_stats"}, 
            {"$set": {
                "server_count": server_count,
                "member_count": member_count,
                "last_updated": discord.utils.utcnow()
            }},
            upsert=True # Створити, якщо такого запису ще немає
        )
        # Розкоментуй рядок нижче, якщо хочеш бачити це в консолі:
        # print(f"[Stats] Updated: {server_count} servers, {member_count} members")

async def setup(bot):
    await bot.add_cog(BotStats(bot))