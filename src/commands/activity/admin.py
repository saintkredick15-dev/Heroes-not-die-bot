import discord
from discord import app_commands
from discord.ext import commands
import json
import datetime
from modules.db import get_database

db = get_database()

def is_admin_or_dev(user_id):
    try:
        with open("../config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        return user_id in config.get("dev", [])
    except:
        return False

def check_permissions(interaction):
    return interaction.user.guild_permissions.administrator or is_admin_or_dev(interaction.user.id)

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

async def update_user_data(guild_id, user_id, update_data):
    await db.users.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": update_data}
    )

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="xp", description="Управління XP користувачів")
    @app_commands.describe(
        дія="Що зробити з XP",
        користувач="Користувач для дії",
        кількість="Кількість XP або рівень"
    )
    @app_commands.choices(дія=[
        app_commands.Choice(name="Додати XP", value="add"),
        app_commands.Choice(name="Забрати XP", value="remove"),
        app_commands.Choice(name="Встановити рівень", value="setlevel"),
        app_commands.Choice(name="Скинути XP", value="reset")
    ])
    async def xp_manage(self, interaction: discord.Interaction, дія: app_commands.Choice[str], 
                       користувач: discord.Member, кількість: int = 0):
        if not check_permissions(interaction):
            await interaction.response.send_message("❌ Недостатньо прав.", ephemeral=True)
            return

        user_data = await get_user_data(interaction.guild.id, користувач.id)

        if дія.value == "add":
            if кількість <= 0:
                await interaction.response.send_message("❌ Кількість XP має бути більше 0.", ephemeral=True)
                return
            await update_user_data(interaction.guild.id, користувач.id, {"xp": user_data["xp"] + кількість})
            await interaction.response.send_message(f"✅ {кількість} XP додано {користувач.mention}.", ephemeral=True)

        elif дія.value == "remove":
            if кількість <= 0:
                await interaction.response.send_message("❌ Кількість XP має бути більше 0.", ephemeral=True)
                return
            new_xp = max(user_data["xp"] - кількість, 0)
            await update_user_data(interaction.guild.id, користувач.id, {"xp": new_xp})
            await interaction.response.send_message(f"🗑️ {кількість} XP забрано у {користувач.mention}.", ephemeral=True)

        elif дія.value == "setlevel":
            if кількість <= 0:
                await interaction.response.send_message("❌ Рівень має бути більше 0.", ephemeral=True)
                return
            await update_user_data(interaction.guild.id, користувач.id, {"level": кількість})
            await interaction.response.send_message(f"🔧 Рівень {користувач.mention} встановлено на {кількість}.", ephemeral=True)

        elif дія.value == "reset":
            await update_user_data(interaction.guild.id, користувач.id, {"xp": 0})
            await interaction.response.send_message(f"🔄 XP {користувач.mention} скинуто до 0.", ephemeral=True)

    @app_commands.command(name="purge", description="Очистити чат")
    @app_commands.describe(період="Період, за який видалити повідомлення")
    @app_commands.choices(період=[
        app_commands.Choice(name="Всі повідомлення", value="all"),
        app_commands.Choice(name="Останні 24 години", value="1d"),
        app_commands.Choice(name="Останні 3 дні", value="3d"),
        app_commands.Choice(name="Останні 7 днів", value="7d"),
        app_commands.Choice(name="Останні 14 днів", value="14d"),
        app_commands.Choice(name="Останні 30 днів", value="30d")
    ])
    async def purge(self, interaction: discord.Interaction, період: app_commands.Choice[str]):
        if not check_permissions(interaction):
            await interaction.response.send_message("❌ Недостатньо прав.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if період.value == "all":
                deleted = await interaction.channel.purge()
                count = len(deleted)
            else:
                days_map = {
                    "1d": 1,
                    "3d": 3,
                    "7d": 7,
                    "14d": 14,
                    "30d": 30
                }
                days = days_map.get(період.value)
                if not days:
                    await interaction.followup.send("❌ Невідомий період.", ephemeral=True)
                    return
                
                cutoff = discord.utils.utcnow() - datetime.timedelta(days=days)
                deleted = await interaction.channel.purge(after=cutoff)
                count = len(deleted)

            await interaction.followup.send(f"✅ Видалено {count} повідомлень.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ У мене немає прав на видалення повідомлень.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Помилка при видаленні: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))