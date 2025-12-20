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
        await self.update_stats_logic()

    @tasks.loop(minutes=5.0)
    async def update_stats(self):
        await self.bot.wait_until_ready()
        await self.update_stats_logic()

    async def update_stats_logic(self):
        try:
            total_server_count = len(self.bot.guilds)
            total_member_count = sum(guild.member_count for guild in self.bot.guilds)
            all_guild_ids = [str(guild.id) for guild in self.bot.guilds]

            await db.site_stats.update_one(
                {"_id": "general_stats"}, 
                {"$set": {
                    "server_count": total_server_count,
                    "member_count": total_member_count,
                    "guild_ids": all_guild_ids,
                    "last_updated": discord.utils.utcnow()
                }},
                upsert=True
            )

            for guild in self.bot.guilds:
                await db.site_stats.update_one(
                    {"_id": str(guild.id)},
                    {"$set": {
                        "guild_id": str(guild.id),
                        "name": guild.name,
                        "member_count": guild.member_count,
                        "icon": str(guild.icon.url) if guild.icon else None,
                        "last_updated": discord.utils.utcnow()
                    }},
                    upsert=True
                )
            
        except Exception as e:
            print(f"Error in update_stats: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        await db.site_stats.update_one(
            {"_id": str(message.guild.id)},
            {"$inc": {"messages_24h": 1}},
            upsert=True
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await db.site_stats.update_one(
            {"_id": str(guild.id)},
            {"$inc": {"mod_actions_24h": 1}},
            upsert=True
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        await db.site_stats.update_one(
            {"_id": str(guild.id)},
            {"$inc": {"mod_actions_24h": 1}},
            upsert=True
        )

async def setup(bot):
    await bot.add_cog(BotStats(bot))