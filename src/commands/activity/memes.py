import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import random

class MemeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="meme", description="Отримати випадковий мем з Reddit")
    async def meme(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Використовуємо meme-api.com для отримання мемів з r/memes
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://meme-api.com/gimme/memes") as response:
                    if response.status != 200:
                        await interaction.followup.send("❌ Не вдалося отримати мем. Спробуйте пізніше.")
                        return
                    
                    data = await response.json()
                    
                    if not data.get("url"):
                         await interaction.followup.send("❌ Прийшов пустий мем :(", ephemeral=True)
                         return

                    embed = discord.Embed(
                        title=data.get("title", "Random Meme"),
                        url=data.get("postLink", "https://reddit.com/r/memes"),
                        color=discord.Color.random()
                    )
                    embed.set_image(url=data["url"])
                    embed.set_footer(text=f"👍 {data.get('ups', 0)} | r/{data.get('subreddit', 'memes')}")

                    await interaction.followup.send(embed=embed)
            
            except Exception as e:
                await interaction.followup.send(f"❌ Сталася помилка: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MemeCommands(bot))
