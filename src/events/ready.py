import discord
from discord.ext import commands
import json

class ReadyEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Logged in as {self.bot.user}')
        
        # Load guild ID from config
        try:
            with open("../config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            guild_id = config.get("guild")
            if guild_id:
                await self.bot.tree.sync(guild=discord.Object(id=guild_id))
        except FileNotFoundError:
            print("Warning: config.json not found, skipping guild sync")

async def setup(bot):
    await bot.add_cog(ReadyEvents(bot))