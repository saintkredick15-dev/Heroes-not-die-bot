import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
from commands.administration.economy_setup import get_eco
from utils.eco_helpers import make_log

db = get_database()

E_COIN = "<:coin:1478487028105482485>"
E_CHECK = "<:cutiecheckmark:1479120440734650389>"
E_CROSS = "<:krestik:1476693091355463842>"

def generate_progress_bar(current: int, total: int, length: int = 15) -> str:
    
    if total <= 0: return "⬜" * length
    percent = min(1.0, current / total)
    filled = int(length * percent)
    empty = length - filled
    return "🟩" * filled + "⬜" * empty

class FundDonateModal(discord.ui.Modal, title="Зробити внесок у Фонд"):
    amount = discord.ui.TextInput(label="Сума внеску", placeholder="1000", max_length=15)

    def __init__(self, eco: dict, view: "FundView"):
        super().__init__()
        self.eco = eco
        self.view = view 

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.amount.value)
            if val <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message(f"{E_CROSS} Будь ласка, введіть коректне число.", ephemeral=True)

        user_id = interaction.user.id
        guild_id = interaction.guild.id
        
        result = await db.users.find_one_and_update(
            {"guild_id": guild_id, "user_id": user_id, "wallet": {"$gte": val}},
            {"$inc": {"wallet": -val}, "$push": {"eco_history": {"$each": [make_log(-val, "Внесок у Фонд Сервера")], "$slice": -50}}}
        )
        if not result:
            return await interaction.response.send_message(f"{E_CROSS} Недостатньо коштів у гаманці під час транзакції!", ephemeral=True)
        
        await db.guild_settings.update_one(
            {"_id": guild_id},
            {"$inc": {"economy.fund_current": val}},
            upsert=True
        )
        from modules.db import invalidate_user_data, invalidate_guild_settings
        await invalidate_user_data(interaction.guild.id, user_id)
        await invalidate_guild_settings(guild_id)
        
        await interaction.response.send_message(f"{E_CHECK} Дякуємо! Ви успішно внесли **{val:,}** {self.eco.get('currency_emoji', E_COIN)} у Фонд Сервера!", ephemeral=True)
        
        from modules.db import get_guild_settings
        settings = await get_guild_settings(db, interaction.guild.id)
        updated_eco = get_eco(settings)
        
        goal = updated_eco.get("fund_goal", 1000000)
        current = updated_eco.get("fund_current", 0)
        curr_emoji = updated_eco.get("currency_emoji", E_COIN)
        
        pct = (current / goal * 100) if goal > 0 else 0
        bar = generate_progress_bar(current, goal, 20)
        
        embed = interaction.message.embeds[0]
        embed.description = (
            f"Разом ми збираємо кошти на глобальні серверні покращення!\n"
            f"Долучайтесь та робіть свій внесок.\n\n"
            f"**Прогрес Збору:**\n"
            f"{bar} **{pct:.1f}%**\n\n"
            f"Зібрано: `{current:,}` / `{goal:,}` {curr_emoji}"
        )
        await interaction.message.edit(embed=embed)

class FundView(discord.ui.View):
    def __init__(self, eco: dict):
        super().__init__(timeout=None)
        self.eco = eco

    @discord.ui.button(label="Внести кошти", style=discord.ButtonStyle.success, emoji="<:Coins:1478486725113286899>")
    async def donate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FundDonateModal(self.eco, self))

class FondsCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="fonds", description="Переглянути Фонд Сервера та зробити внесок")
    async def fonds_cmd(self, interaction: discord.Interaction):
        from modules.db import get_guild_settings
        settings = await get_guild_settings(db, interaction.guild.id)
        eco = get_eco(settings)
        
        if not eco.get("enabled", True):
            return await interaction.response.send_message(f"{E_CROSS} Економіка вимкнена.", ephemeral=True)
            
        if not eco.get("fund_enabled", False):
            return await interaction.response.send_message(f"{E_CROSS} Фонд Сервера наразі вимкнений.", ephemeral=True)
            
        goal = eco.get("fund_goal", 1000000)
        current = eco.get("fund_current", 0)
        curr_emoji = eco.get("currency_emoji", E_COIN)
        
        pct = (current / goal * 100) if goal > 0 else 0
        bar = generate_progress_bar(current, goal, 20)
        
        embed = discord.Embed(
            title="🏦 Фонд Сервера",
            description=(
                f"Разом ми збираємо кошти на глобальні серверні покращення!\n"
                f"Долучайтесь та робіть свій внесок.\n\n"
                f"**Прогрес Збору:**\n"
                f"{bar} **{pct:.1f}%**\n\n"
                f"Зібрано: `{current:,}` / `{goal:,}` {curr_emoji}"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        await interaction.response.send_message(embed=embed, view=FundView(eco))

async def setup(bot):
    await bot.add_cog(FondsCommand(bot))
