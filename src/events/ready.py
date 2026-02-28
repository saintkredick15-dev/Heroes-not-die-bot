import discord
from discord.ext import commands


class ReadyEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user}")
        # Примітка: tree.sync() викликається в bot.py → setup_hook.
        # Дублювати його тут не потрібно і шкідливо (витрачає ліміт 200 req/день).


async def setup(bot):
    await bot.add_cog(ReadyEvents(bot))