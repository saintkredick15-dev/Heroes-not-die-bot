import discord
from discord.ext import commands, tasks

from modules.db import get_database
from services.stats_contract import aggregate_guild_analytics, build_site_stats_snapshot

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
            total_member_count = sum(guild.member_count or 0 for guild in self.bot.guilds)
            all_guild_ids = [str(guild.id) for guild in self.bot.guilds]
            now = discord.utils.utcnow()

            await db.site_stats.update_one(
                {"_id": "general_stats"},
                {
                    "$set": {
                        "server_count": total_server_count,
                        "member_count": total_member_count,
                        "guild_ids": all_guild_ids,
                        "last_updated": now,
                    }
                },
                upsert=True,
            )

            for guild in self.bot.guilds:
                stats_24h = await aggregate_guild_analytics(guild.id, 1, collection=db.guild_analytics, now=now)
                stats_7d = await aggregate_guild_analytics(guild.id, 7, collection=db.guild_analytics, now=now)
                stats_30d = await aggregate_guild_analytics(guild.id, 30, collection=db.guild_analytics, now=now)

                snapshot = build_site_stats_snapshot(
                    guild_id=guild.id,
                    guild_name=guild.name,
                    member_count=guild.member_count,
                    icon_url=str(guild.icon.url) if guild.icon else None,
                    stats_24h=stats_24h,
                    stats_7d=stats_7d,
                    stats_30d=stats_30d,
                    now=now,
                )

                await db.site_stats.update_one(
                    {"_id": str(guild.id)},
                    {
                        "$set": snapshot,
                        "$unset": {
                            "messages_24h": "",
                            "mod_actions_24h": "",
                        },
                    },
                    upsert=True,
                )

        except Exception as e:
            print(f"Error in update_stats: {e}")


async def setup(bot):
    await bot.add_cog(BotStats(bot))
