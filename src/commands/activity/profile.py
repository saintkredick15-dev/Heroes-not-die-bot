import io
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from modules.db import get_database

db = get_database()

async def get_user_data(guild_id, user_id):
    user = await db.users.find_one({"guild_id": guild_id, "user_id": user_id})
    if not user:
        user = {
            "guild_id": guild_id,
            "user_id": user_id,
            "xp": 0,
            "level": 1,
            "messages": 0,
            "voice_minutes": 0,
            "reactions": 0,
            "history": {}
        }
        await db.users.insert_one(user)
    return user

def get_level_xp(level):
    return 5 * (level ** 2) + 50 * level + 100

class ProfileCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Показує профіль користувача")
    @app_commands.describe(user="Користувач (за замовчуванням - ти)")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer(ephemeral=False)

        try:
            target_user = user or interaction.user
            user_data = await get_user_data(interaction.guild.id, target_user.id)

            current_level = user_data.get("level", 0)
            xp = user_data.get("xp", 0)
            xp_needed = get_level_xp(current_level)
            xp_percent = round((xp / xp_needed) * 100) if xp_needed else 0

            voice_minutes = user_data.get("voice_minutes", 0)
            voice_hours = round(voice_minutes / 60, 1)

            roles = [
                role.name for role in sorted(target_user.roles, key=lambda r: r.position, reverse=True)
                if role.name != "@everyone"
            ][:3]
            roles_display = ", ".join(roles) if roles else "Немає"
            joined_at = target_user.joined_at.strftime("%d %B %Y") if target_user.joined_at else "Невідомо"

            history = user_data.get("history", {})
            days = [datetime.now() - timedelta(days=i) for i in reversed(range(7))]
            labels = [day.strftime('%a') for day in days]
            xp_values = [history.get(day.strftime("%Y-%m-%d"), 0) for day in days]

            plt.figure(figsize=(8, 4))
            plt.plot(labels, xp_values, marker='o', linestyle='-', color='royalblue')
            plt.title('Активність (XP за останні 7 днів)')
            plt.xlabel('День тижня')
            plt.ylabel('Отримано XP')
            plt.grid(True, color='darkgray')
            plt.tight_layout()

            image_bytes = io.BytesIO()
            plt.savefig(image_bytes, format='png')
            plt.close()
            image_bytes.seek(0)

            filename = "profile_graph.png"
            file = discord.File(fp=image_bytes, filename=filename)

            profile_embed = discord.Embed(
                title=f"Профіль {target_user.display_name}",
                description="\n".join([
                    f"**Учасник з:** {joined_at}\n",
                    f"**Рівень:** {current_level}",
                    f"**XP:** {xp}/{xp_needed} ({xp_percent}%)",
                    f"**Voice:** {voice_hours} год",
                    f"**Реакцій:** {user_data.get('reactions', 0)}",
                    f"**Повідомлень:** {user_data.get('messages', 0)}\n",
                    f"**Ролі:** {roles_display}"
                ]),
                color=0x36393F
            )

            profile_embed.set_image(url=f"attachment://{filename}")
            profile_embed.set_thumbnail(url=target_user.display_avatar.url)

            await interaction.followup.send(embed=profile_embed, file=file)

        except Exception as e:
            await interaction.followup.send(f"⚠️ Помилка при завантаженні профілю: `{e}`")

async def setup(bot):
    await bot.add_cog(ProfileCommands(bot))
