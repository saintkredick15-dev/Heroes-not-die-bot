import discord
from discord.ext import commands


class ReadyEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user}")
        # Automatic tree.sync() on startup is disabled.
        # Use the owner/dev text command !sync after command schema changes.


async def setup(bot):
    await bot.add_cog(ReadyEvents(bot))
