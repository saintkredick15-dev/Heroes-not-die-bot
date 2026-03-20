import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import random
from modules.db import get_database

db = get_database()

class MemeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="meme", description="Отримати випадковий мем з Reddit")
    async def meme(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_id = interaction.guild_id
        guild_data = await db.guilds.find_one({"guild_id": guild_id})
        seen_memes = guild_data.get("seen_memes", []) if guild_data else []

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://meme-api.com/gimme/memes/50") as response:
                    if response.status != 200:
                        await interaction.followup.send("<:cutiex:1480246146076119132> Не вдалося отримати мем. Спробуйте пізніше.")
                        return
                    
                    data = await response.json()
                    memes = data.get("memes", [])
                    
                    if not memes:
                         await interaction.followup.send("<:cutiex:1480246146076119132> Прийшов пустий список мемів :(", ephemeral=True)
                         return

                    selected_meme = None
                    for meme in memes:
                        if meme["url"] not in seen_memes:
                            selected_meme = meme
                            break
                    
                    if not selected_meme:
                        selected_meme = random.choice(memes)

                    embed = discord.Embed(
                        title=selected_meme.get("title", "Random Meme"),
                        url=selected_meme.get("postLink", "https://reddit.com/r/memes"),
                        color=0x1a1a2e,
                    )
                    embed.set_image(url=selected_meme["url"])
                    embed.set_footer(
                        text=f"{selected_meme.get('ups', 0)} upvotes  •  r/{selected_meme.get('subreddit', 'memes')}"
                    )

                    await interaction.followup.send(embed=embed)

                    new_seen = seen_memes + [selected_meme["url"]]
                    
                    if len(new_seen) > 200:
                        new_seen = new_seen[-200:]
                    
                    await db.guilds.update_one(
                        {"guild_id": guild_id},
                        {"$set": {"seen_memes": new_seen}},
                        upsert=True
                    )
            
            except aiohttp.ClientError:
                await interaction.followup.send("<:cutiex:1480246146076119132> Помилка мережі. Спробуйте пізніше.", ephemeral=True)
            except discord.HTTPException as e:
                await interaction.followup.send(f"<:cutiex:1480246146076119132> Помилка Discord: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MemeCommands(bot))
