import discord
from discord.ext import commands
import asyncio
from modules.logger import Logger

log = Logger("Tickets")

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Закрити тікет", style=discord.ButtonStyle.red, custom_id="ticket_close_v2")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Тікет буде закрито через 5 секунд...", ephemeral=True)
        await asyncio.sleep(5)
        await interaction.channel.delete()

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Створити тікет", style=discord.ButtonStyle.blurple, emoji="🎫", custom_id="ticket_create_v2")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        # Перевірка чи вже є тікет (пошук каналу з топіком ID користувача, або просто по назві)
        # Для простоти поки що перевіряємо назву, це не ідеально але працює для V1
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            category = await guild.create_category("Tickets")

        channel_name = f"ticket-{user.name}".lower().replace(" ", "-") # Discord channel name restrictions
        
        existing_channel = discord.utils.get(guild.text_channels, name=channel_name, category_id=category.id)
        if existing_channel:
            await interaction.response.send_message(f"У вас вже є відкритий тікет: {existing_channel.mention}", ephemeral=True)
            return

        # Налаштування прав
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"User ID: {user.id}"
            )
        except Exception as e:
            await interaction.response.send_message(f"Помилка при створенні каналу: {e}", ephemeral=True)
            log.error(f"Failed to create ticket channel for {user}: {e}")
            return

        await interaction.response.send_message(f"Тікет створено: {channel.mention}", ephemeral=True)

        embed = discord.Embed(
            title="Служба підтримки",
            description=f"Привіт {user.mention}! Опишіть вашу проблему, і адміністрація зв'яжеться з вами найближчим часом.",
            color=discord.Color.green()
        )
        
        await channel.send(embed=embed, view=TicketControlView())


class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketControlView())
        log.info("Ticket views registered")

    @commands.command(name="setup_tickets")
    @commands.has_permissions(administrator=True)
    async def setup_tickets(self, ctx):
        """Встановлює панель створення тікетів"""
        embed = discord.Embed(
            title="🎫 Створити тікет",
            description="Натисніть кнопку нижче, щоб зв'язатися з адміністрацією.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed, view=TicketView())
        await ctx.message.delete()

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
