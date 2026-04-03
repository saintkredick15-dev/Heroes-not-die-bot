import discord
from discord import app_commands
from discord.ext import commands

from commands.administration.economy_setup_shared import get_eco
from modules.db import get_database
from utils.ui_contract import add_section, set_surface_footer, surface_embed

db = get_database()

E_AUCTION = "<:hammer:1485606127696609412>"


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
            return await interaction.followup.send(
                "Аукціон ще не налаштований адміністратором: канал для лотів не обраний.",
                ephemeral=True,
            )

        embed = surface_embed(
            "gameplay",
            f"{E_AUCTION} Аукціон",
            "Це оглядовий екран системи лотів і ставок сервера.",
            tone="warning",
        )
        add_section(
            embed,
            "Поточний стан",
            [
                f"Канал проведення: <#{channel_id}>",
                "Розклад і деталі лотів з'являтимуться тут після публікації аукціонів.",
            ],
        )
        set_surface_footer(embed, "gameplay", "Поки що це оглядовий екран, не live-торги.")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AuctionCommand(bot))
