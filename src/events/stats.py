import discord
from discord.ext import commands, tasks
from src.modules.db import get_database

db = get_database()

class BotStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_stats.start()

    def cog_unload(self):
        self.update_stats.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Запускаємо оновлення одразу, як бот прокинувся"""
        print("[Stats] Бот готовий, оновлюю статистику...")
        await self.update_stats_logic()

    @tasks.loop(minutes=5.0)
    async def update_stats(self):
        """Регулярне оновлення"""
        await self.bot.wait_until_ready()
        await self.update_stats_logic()

    async def update_stats_logic(self):
        try:
            server_count = len(self.bot.guilds)
            member_count = sum(guild.member_count for guild in self.bot.guilds)
            
            # Отримуємо ID серверів
            guild_ids = [str(guild.id) for guild in self.bot.guilds]
            
            # Оновлюємо базу
            await db.site_stats.update_one(
                {"_id": "general_stats"}, 
                {"$set": {
                    "server_count": server_count,
                    "member_count": member_count,
                    "guild_ids": guild_ids,
                    "last_updated": discord.utils.utcnow()
                }},
                upsert=True
            )
            print(f"✅ [Stats] Успішно записано в базу: {server_count} серверів.")
        except Exception as e:
            print(f"❌ [Stats] Помилка запису в базу: {e}")

async def setup(bot):
    await bot.add_cog(BotStats(bot))