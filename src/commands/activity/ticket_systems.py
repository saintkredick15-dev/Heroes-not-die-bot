import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from modules.db import get_database
from modules.logger import Logger

db = get_database()
log = Logger("Tickets")

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label="Відкрити", style=discord.ButtonStyle.primary, custom_id="ticket_btn_open", emoji="🎫")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction)

    async def create_ticket(self, interaction: discord.Interaction):
        # Одразу відповідаємо Discord, щоб уникнути "Interaction failed"
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Перевірка на вже відкритий тікет
            existing_ticket = await db.tickets.find_one({
                "guild_id": interaction.guild.id,
                "user_id": interaction.user.id,
                "status": "open"
            })

            if existing_ticket:
                channel = interaction.guild.get_channel(existing_ticket["channel_id"])
                if channel:
                    await interaction.followup.send(
                        f"У вас вже є відкритий тікет: {channel.mention}",
                        ephemeral=True
                    )
                    return
                else:
                    # Якщо канал не знайдено (видалений вручну), оновлюємо статус в базі
                    await db.tickets.update_one(
                        {"_id": existing_ticket["_id"]},
                        {"$set": {"status": "closed_manually"}}
                    )

            # Отримуємо конфігурацію гільдії (для ролей модераторів і категорії)
            guild_config = await db.ticket_config.find_one({"guild_id": interaction.guild.id})
            moderator_role_ids = guild_config.get("moderator_role_ids", []) if guild_config else []
            
            # Створення каналу
            # Спробуємо знайти категорію "Tickets" або створити нову
            category = discord.utils.get(interaction.guild.categories, name="Tickets")
            if not category:
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
                }
                category = await interaction.guild.create_category("Tickets", overwrites=overwrites)

            # Права доступу для тікета
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }

            # Додаємо ролі модераторів
            for role_id in moderator_role_ids:
                role = interaction.guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            ticket_name = f"ticket-{interaction.user.name}"
            
            channel = await interaction.guild.create_text_channel(
                name=ticket_name,
                category=category,
                overwrites=overwrites
            )

            # Запис в базу
            await db.tickets.insert_one({
                "guild_id": interaction.guild.id,
                "channel_id": channel.id,
                "user_id": interaction.user.id,
                "created_at": datetime.now(),
                "status": "open"
            })

            # Повідомлення в тікеті
            embed = discord.Embed(
                title="Тікет відкрито",
                description=f"Привіт {interaction.user.mention}! Опишіть вашу проблему, і модератори скоро зв'яжуться з вами.",
                color=discord.Color.green()
            )
            
            close_view = TicketCloseView()
            await channel.send(embed=embed, view=close_view)
            
            await interaction.followup.send(f"Тікет створено: {channel.mention}", ephemeral=True)

        except Exception as e:
            log.error(f"Error creating ticket: {e}")
            await interaction.followup.send(f"Виникла помилка при створенні тікета: {e}", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Закрити", style=discord.ButtonStyle.red, custom_id="ticket_btn_close", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            # Логіка закриття
            await db.tickets.update_one(
                {"channel_id": interaction.channel_id},
                {"$set": {"status": "closed", "closed_at": datetime.now()}}
            )
            await interaction.channel.delete()
        except Exception as e:
            log.error(f"Error closing ticket: {e}")
            await interaction.followup.send(f"Помилка при закритті: {e}", ephemeral=True)

class TicketSystems(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Реєструємо персистентні view при запуску
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketCloseView())

    @app_commands.command(name="tickets", description="Створити панель тікетів")
    @app_commands.describe(
        channel="Канал для відправки панелі",
        title="Заголовок для embed повідомлення",
        description="Текст опису",
        button_label="Текст на кнопці",
        image_url="Посилання на картинку (опціонально)"
    )
    async def tickets(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel, 
        description: str,
        title: str = "Відкрий тикет",
        button_label: str = "Відкрити",
        image_url: str = None
    ):
        await interaction.response.defer(ephemeral=True)
        
        # Перевірка прав (тільки для адмінів)
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("Ця команда доступна тільки адміністраторам.", ephemeral=True)
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x2b2d31
        )
        embed.set_footer(text="Powered by bot")
        
        if image_url:
            embed.set_image(url=image_url)

        # Створення кнопки з параметрами користувача
        view = discord.ui.View(timeout=None)
        button = discord.ui.Button(
            label=button_label,
            style=discord.ButtonStyle.primary,
            custom_id="ticket_btn_open",
            emoji="🎫"
        )
        view.add_item(button)

        await channel.send(embed=embed, view=view)
        await interaction.followup.send(f"Панель тікетів успішно створено в каналі {channel.mention}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystems(bot))
