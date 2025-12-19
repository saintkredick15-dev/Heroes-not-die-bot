import discord
from discord import app_commands
from discord.ext import commands
import json
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

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))