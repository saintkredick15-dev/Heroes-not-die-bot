import discord
from discord.ext import commands
import json
import os

class ReadyEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Logged in as {self.bot.user}')
        
        # Сінхронізація команд (щоб вони з'явилися на сервері)
        try:
            synced = await self.bot.tree.sync()
            print(f"Synced {len(synced)} command(s) globally.")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

async def setup(bot):
    await bot.add_cog(ReadyEvents(bot))