import discord
from discord import app_commands
from discord.ext import commands
import time
import asyncio

from modules.db import get_database
from commands.administration.economy_setup import get_eco

db = get_database()

E_COIN = "<:coin:1478487028105482485>"
E_AUCTION = "<:Auction:1479863712855621805>"
E_CLOCK = "<:clock:1476209087804084328>"

class AuctionCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="auction", description="Переглянути активні та майбутні лоти на аукціоні")
    async def auction_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from modules.db import get_guild_settings
        settings = await get_guild_settings(db, interaction.guild.id)
        eco = get_eco(settings)
        
        if not eco.get("enabled", True):
            return await interaction.followup.send("Економіка вимкнена.", ephemeral=True)
            
        channel_id = eco.get("auction_channel_id", 0)
        if channel_id == 0:
            return await interaction.followup.send("Аукціон ще не налаштований адміністратором (канал не обрано).", ephemeral=True)
            
        embed = discord.Embed(
            title=f"{E_AUCTION} Чорний Ринок — Аукціон",
            description=f"Канал проведення: <#{channel_id}>\n\nНаразі система аукціонів знаходиться в розробці. Незабаром тут з'явиться розклад лотів!",
            color=0x1a1a2e
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AuctionCommand(bot))
