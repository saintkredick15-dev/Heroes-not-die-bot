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
    @app_commands.default_permissions(administrator=True)
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
    @app_commands.default_permissions(administrator=True)
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

    @app_commands.command(name="kick", description="Вигнати користувача з серверу")
    @app_commands.describe(користувач="Користувач, якого потрібно вигнати", причина="Причина вигнання")
    @app_commands.default_permissions(administrator=True)
    async def kick(self, interaction: discord.Interaction, користувач: discord.Member, причина: str = "Не вказана"):
        if not check_permissions(interaction):
            await interaction.response.send_message("❌ Недостатньо прав.", ephemeral=True)
            return

        if користувач.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ Ви не можете вигнати цього користувача.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            await користувач.send(f"Ви були вигнані з серверу **{interaction.guild.name}**. Причина: {причина}")
        except:
            pass

        try:
            await користувач.kick(reason=причина)
            await interaction.followup.send(f"👢 {користувач.mention} був вигнаний. Причина: {причина}")
        except discord.Forbidden:
            await interaction.followup.send("❌ У мене немає прав на вигнання цього користувача.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Забанити користувача на сервері")
    @app_commands.describe(користувач="Користувач, якого потрібно забанити", причина="Причина бану")
    @app_commands.default_permissions(administrator=True)
    async def ban(self, interaction: discord.Interaction, користувач: discord.Member, причина: str = "Не вказана"):
        if not check_permissions(interaction):
            await interaction.response.send_message("❌ Недостатньо прав.", ephemeral=True)
            return

        if користувач.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ Ви не можете забанити цього користувача.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            await користувач.send(f"Ви були забанені на сервері **{interaction.guild.name}**. Причина: {причина}")
        except:
            pass

        try:
            await користувач.ban(reason=причина)
            await interaction.followup.send(f"🔨 {користувач.mention} був забанений. Причина: {причина}")
        except discord.Forbidden:
            await interaction.followup.send("❌ У мене немає прав на бан цього користувача.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка: {e}", ephemeral=True)

    @app_commands.command(name="mute", description="Тимчасово заборонити користувачу писати (Timeout)")
    @app_commands.describe(користувач="Користувач", час="Тривалість (напр. 10m, 1h, 1d)", причина="Причина")
    @app_commands.default_permissions(administrator=True)
    async def mute(self, interaction: discord.Interaction, користувач: discord.Member, час: str, причина: str = "Не вказана"):
        if not check_permissions(interaction):
            await interaction.response.send_message("❌ Недостатньо прав.", ephemeral=True)
            return

        if користувач.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ Ви не можете замутити цього користувача.", ephemeral=True)
            return

        # Парсинг часу
        seconds = 0
        try:
            if час.endswith("m"):
                seconds = int(час[:-1]) * 60
            elif час.endswith("h"):
                seconds = int(час[:-1]) * 3600
            elif час.endswith("d"):
                seconds = int(час[:-1]) * 86400
            elif час.endswith("s"):
                seconds = int(час[:-1])
            else:
                await interaction.response.send_message("❌ Невірний формат часу. Використовуйте m, h, d (напр. 10m).", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Невірний формат часу.", ephemeral=True)
            return

        if seconds <= 0:
             await interaction.response.send_message("❌ Час має бути більше 0.", ephemeral=True)
             return

        duration = datetime.timedelta(seconds=seconds)
        
        await interaction.response.defer()
        try:
            await користувач.timeout(duration, reason=причина)
            await interaction.followup.send(f"🔇 {користувач.mention} отримав мут на {час}. Причина: {причина}")
            try:
                await користувач.send(f"Ви отримали мут на сервері **{interaction.guild.name}** на {час}. Причина: {причина}")
            except:
                pass
        except discord.Forbidden:
            await interaction.followup.send("❌ У мене немає прав на мут цього користувача.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка: {e}", ephemeral=True)

    @app_commands.command(name="unmute", description="Зняти мут з користувача")
    @app_commands.describe(користувач="Користувач")
    @app_commands.default_permissions(administrator=True)
    async def unmute(self, interaction: discord.Interaction, користувач: discord.Member):
        if not check_permissions(interaction):
            await interaction.response.send_message("❌ Недостатньо прав.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            await користувач.timeout(None)
            await interaction.followup.send(f"🔊 З {користувач.mention} знято мут.")
        except discord.Forbidden:
            await interaction.followup.send("❌ У мене немає прав.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))