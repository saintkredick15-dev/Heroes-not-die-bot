import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database

db = get_database()

class LeaderboardCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Показує топ користувачів")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        users = await db.users.find({"guild_id": interaction.guild.id}).to_list(1000)

        def get_score(user):
            return user.get("xp", 0) + user.get("level", 0) * 1000

        # Фільтруємо тільки користувачів, які є на сервері
        active_users = []
        for user_data in users:
            member = interaction.guild.get_member(user_data.get("user_id"))
            if member:  # Додаємо тільки якщо користувач є на сервері
                active_users.append(user_data)

        sorted_users = sorted(active_users, key=get_score, reverse=True)

        leaderboard_lines = ["📊 ЛІДЕРБОРД\n"]
        author_id = str(interaction.user.id)
        found_author = False

        for i, user_data in enumerate(sorted_users[:20], start=1):
            member = interaction.guild.get_member(user_data.get("user_id"))
            name = member.display_name

            # Конвертуємо хвилини в години
            voice_minutes = user_data.get('voice_minutes', 0)
            voice_hours = round(voice_minutes / 60, 1)

            line = (
                f"{i:>2}. {name:<20} | "
                f"Lvl: {user_data.get('level', 0):<2} | "
                f"XP: {user_data.get('xp', 0):<4} | "
                f"Voice: {voice_hours} год | "
                f"Реакцій: {user_data.get('reactions', 0)}"
            )
            leaderboard_lines.append(line)

            if user_data.get("user_id") == interaction.user.id:
                found_author = True

        if not found_author:
            for i, user_data in enumerate(sorted_users, start=1):
                if user_data.get("user_id") == interaction.user.id:
                    # Конвертуємо хвилини в години для позиції користувача
                    voice_minutes = user_data.get('voice_minutes', 0)
                    voice_hours = round(voice_minutes / 60, 1)
                    
                    line = (
                        f"\nТи на {i} місці:\n"
                        f"Lvl: {user_data.get('level', 0)} | XP: {user_data.get('xp', 0)} | "
                        f"Voice: {voice_hours} год | Реакцій: {user_data.get('reactions', 0)}"
                    )
                    leaderboard_lines.append(line)
                    break

        result = "```\n" + "\n".join(leaderboard_lines) + "\n```"
        await interaction.followup.send(result)

async def setup(bot):
    await bot.add_cog(LeaderboardCommands(bot))