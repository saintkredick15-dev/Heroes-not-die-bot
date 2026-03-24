import discord
from discord import app_commands
from discord.ext import commands
from config.constants import Emojis

class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="avatar", description="Отримати аватар будь-якого користувача у повному розмірі")
    @app_commands.describe(member="Користувач, аватар якого ви хочете побачити")
    async def avatar(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        """Отримати аватар користувача"""
        
        target = member or interaction.user
        
        avatar_url = target.avatar.url if target.avatar else target.default_avatar.url

        embed = discord.Embed(
            title=f"Аватар {target.display_name}",
            color=0x36393F  
        )
        embed.set_image(url=avatar_url)
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="Завантажити оригінал",
            url=avatar_url,
            style=discord.ButtonStyle.link,
            emoji=discord.PartialEmoji.from_str(Emojis.SEARCH.value)
        ))

        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
