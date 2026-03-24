import discord
from discord import app_commands
from discord.ext import commands
import io
import time
from datetime import datetime, timedelta

try:
    import matplotlib
    matplotlib.use('Agg') 
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from modules.db import get_database

db = get_database()

class AddAccessModal(discord.ui.Modal, title="Додати доступ до /dev_stats"):
    user_id_input = discord.ui.TextInput(
        label="ID користувача",
        placeholder="Введіть Discord ID...",
        min_length=17,
        max_length=25
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
            
            await db.bot_settings.update_one({"_id": "dev_access"}, {"$addToSet": {"allowed_users": uid}}, upsert=True)
            await interaction.response.send_message(f"<:check:1485597845883981905> Доступ надано користувачу з ID `{uid}`.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("<:close:1485598320935174317> Невірний формат ID.", ephemeral=True)

class RemoveAccessModal(discord.ui.Modal, title="Забрати доступ до /dev_stats"):
    user_id_input = discord.ui.TextInput(
        label="ID користувача",
        placeholder="Введіть Discord ID...",
        min_length=17,
        max_length=25
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
            
            await db.bot_settings.update_one({"_id": "dev_access"}, {"$pull": {"allowed_users": uid}}, upsert=True)
            await interaction.response.send_message(f"<:check:1485597845883981905> Доступ забрано у користувача з ID `{uid}`.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("<:close:1485598320935174317> Невірний формат ID.", ephemeral=True)

class DevStatsView(discord.ui.View):
    def __init__(self, cog: 'DevStatsCommand', user: discord.User, guild_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user = user
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("<:close:1485598320935174317> Ви не можете використовувати ці кнопки.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Всеосяжна статистика", style=discord.ButtonStyle.secondary, custom_id="dev_stats_global", emoji="<:search:1485637936165949543>")
    async def btn_global(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, file = await self.cog.get_stats_embed(global_stats=True)
        try:
            if file:
                await interaction.edit_original_response(embed=embed, attachments=[file])
            else:
                await interaction.edit_original_response(embed=embed, attachments=[])
        except Exception as e:
            pass

    @discord.ui.button(label="Діючий сервер", style=discord.ButtonStyle.secondary, custom_id="dev_stats_local", emoji="<:stats:1485607826964353144>")
    async def btn_local(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, file = await self.cog.get_stats_embed(global_stats=False, guild_id=self.guild_id, guild_name=interaction.guild.name)
        try:
            if file:
                await interaction.edit_original_response(embed=embed, attachments=[file])
            else:
                await interaction.edit_original_response(embed=embed, attachments=[])
        except Exception as e:
            pass

    @discord.ui.button(label="Додати доступ", style=discord.ButtonStyle.secondary, custom_id="dev_stats_access", emoji="<:shield_check:1485606912073400330>")
    async def btn_access(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        await interaction.response.send_modal(AddAccessModal(self.cog.bot))

    @discord.ui.button(label="Забрати доступ", style=discord.ButtonStyle.secondary, custom_id="dev_stats_remove_access", emoji="<:shield:1485606277081071666>")
    async def btn_remove_access(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveAccessModal(self.cog.bot))

def is_owner_or_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == 961262391314755665 or await interaction.client.is_owner(interaction.user):
            return True
        doc = await db.bot_settings.find_one({"_id": "dev_access"})
        if doc and interaction.user.id in doc.get("allowed_users", []):
            return True
        return False
    return app_commands.check(predicate)

class DevStatsCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        pass

    async def get_server_snapshot(self, guild_id: int) -> dict:
        cursor = db.users.find({"guild_id": guild_id})
        wallets = await cursor.to_list(length=None)
        
        active_wallets = len([w for w in wallets if w.get("wallet", 0) > 0 or w.get("bank", 0) > 0])
        total_in_wallets = sum(w.get("wallet", 0) for w in wallets)
        total_in_banks = sum(w.get("bank", 0) for w in wallets)
        total_earned = sum(w.get("total_earned", 0) for w in wallets)
        total_money = total_in_wallets + total_in_banks
        
        settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
        eco = settings.get("economy", {})
        inflation_mult = eco.get("inflation_multiplier", 1.0)
        
        return {
            "timestamp": int(time.time()),
            "guild_id": guild_id,
            "active_wallets": active_wallets,
            "total_money": total_money,
            "total_earned": total_earned,
            "inflation_mult": inflation_mult
        }

    async def ensure_snapshot_saved(self, guild_id: int):
        now = int(time.time())
        last_snap = await db.server_analytics.find_one(
            {"guild_id": guild_id}, 
            sort=[("timestamp", -1)]
        )
        
        if not last_snap or (now - last_snap["timestamp"]) > 3600:
            snapshot = await self.get_server_snapshot(guild_id)
            await db.server_analytics.insert_one(snapshot)

    async def get_stats_embed(self, global_stats: bool = False, guild_id: int = None, guild_name: str = None):
        if not global_stats:
            await self.ensure_snapshot_saved(guild_id)
            cursor = db.server_analytics.find({"guild_id": guild_id}).sort("timestamp", 1).limit(100)
            history = await cursor.to_list(length=100)
            
            if not history:
                return discord.Embed(description="📉 Недостатньо даних.", color=0x2b2d31), None
                
            current = history[-1]
            title = f"📊 Аналітика: {guild_name}"
            inc_percent = (current.get('inflation_mult', 1.0) - 1.0) * 100
        else:
            
            cursor = db.users.find()
            total_money = 0
            total_earned = 0
            active_wallets = 0
            async for u in cursor:
                w = u.get("wallet", 0)
                b = u.get("bank", 0)
                if w > 0 or b > 0:
                    active_wallets += 1
                total_money += (w + b)
                total_earned += u.get("total_earned", 0)
                
            title = "📊 Всеосяжна статистика (Global)"
            inc_percent = 0.0 
            history = [] 
            current = {
                "active_wallets": active_wallets,
                "total_money": total_money,
                "total_earned": total_earned,
            }

        embed = discord.Embed(
            title=title,
            color=0x2b2d31,
            description="Глобальна статистика економічних процесів." if not global_stats else "Статистика по всіх серверах бота."
        )
        embed.add_field(name="<:wallet:1485625593574850720> Всього валюти (В обороті)", value=f"**{current.get('total_money', 0):,}**", inline=True)
        embed.add_field(name="<:stats:1485607826964353144> Згенеровано за весь час", value=f"**{current.get('total_earned', 0):,}**", inline=True)
        embed.add_field(name="<:check:1485597845883981905> Активних гаманців", value=f"**{current.get('active_wallets', 0)}**", inline=True)
        
        if not global_stats:
            embed.add_field(name="<:flame:1485618663489929356> Відсоток інфляції", value=f"**+{inc_percent:.4f}%**", inline=True)

        file = None
        if not global_stats and HAS_MATPLOTLIB and len(history) > 1:
            try:
                timestamps = [datetime.fromtimestamp(snap["timestamp"]) for snap in history]
                totals = [snap.get("total_money", 0) for snap in history]
                
                if len(history) < 3:
                     timestamps.insert(0, timestamps[0] - timedelta(hours=12))
                     totals.insert(0, totals[0] * 0.9)
                
                plt.style.use('dark_background')
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.plot(timestamps, totals, color='#5865F2', marker='o', linestyle='-', linewidth=2, markersize=4)
                ax.fill_between(timestamps, totals, alpha=0.2, color='#5865F2')
                ax.set_title('Грошова маса в обороті (Trend)', color='white')
                ax.set_ylabel('Всього монет', color='lightgray')
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
                plt.xticks(rotation=45)
                ax.grid(True, linestyle='--', alpha=0.3)
                
                for spine in ax.spines.values():
                    spine.set_visible(False)
                    
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png', facecolor='#2b2d31', edgecolor='none')
                buf.seek(0)
                plt.close(fig)
                
                file = discord.File(buf, filename="chart.png")
                embed.set_image(url="attachment://chart.png")
            except Exception as e:
                embed.set_footer(text=f"Не вдалося згенерувати графік: {e}")

        return embed, file

    @app_commands.command(name="dev_stats", description="[OWNER ONLY] Аналітика та графіки економіки сервера")
    @is_owner_or_admin()
    async def dev_stats(self, interaction: discord.Interaction):
        
        embed = discord.Embed(
            title="🛠️ Панель розробника",
            description="Оберіть яку статистику ви хочете переглянути, або видайте доступ іншим розробникам.",
            color=0x2b2d31
        )
        view = DevStatsView(self, interaction.user, interaction.guild.id)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(DevStatsCommand(bot))
