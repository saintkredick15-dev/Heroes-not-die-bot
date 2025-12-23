import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import traceback
import sys
import asyncio
from modules.db import get_database
from modules.logger import Logger

# Ініціалізація
db = get_database()
log = Logger("Tickets")

# --- DEBUG HELPER ---
def debug_log(message):
    print(f"[TICKET_DEBUG] {message}")
    sys.stdout.flush()

# --- CONFIGURATION VIEWS ---
class TicketConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Виберіть ролі підтримки (Support Roles)",
        min_values=0,
        max_values=20,
        custom_id="ticket_config_roles"
    )
    async def select_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await interaction.response.defer(ephemeral=True)
        role_ids = [role.id for role in select.values]
        
        await db.ticket_config.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"support_role_ids": role_ids}},
            upsert=True
        )
        
        role_names = [role.name for role in select.values]
        await interaction.followup.send(
            f"✅ **Ролі підтримки оновлено!**\nВибрано: {', '.join(role_names)}", 
            ephemeral=True
        )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.category],
        placeholder="Виберіть категорію для тікетів",
        min_values=1,
        max_values=1,
        custom_id="ticket_config_category"
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer(ephemeral=True)
        category = select.values[0]
        
        await db.ticket_config.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"ticket_category_id": category.id}},
            upsert=True
        )
        
        await interaction.followup.send(
            f"✅ **Категорію оновлено!**\nТікети будуть створюватись у: **{category.name}**", 
            ephemeral=True
        )

# --- MAIN TICKET LOGIC ---

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label="Відкрити", style=discord.ButtonStyle.primary, custom_id="ticket_btn_open", emoji="🎫")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction)

    async def create_ticket(self, interaction: discord.Interaction):
        # 1. Defer immediately
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            debug_log(f"Defer failed: {e}")
            return

        try:
            # 2. Check existing tickets
            existing = await db.tickets.find_one({
                "guild_id": interaction.guild.id, 
                "user_id": interaction.user.id, 
                "status": "open"
            })
            if existing:
                channel = interaction.guild.get_channel(existing["channel_id"])
                if channel:
                    await interaction.followup.send(f"⚠️ Вже є відкритий тікет: {channel.mention}", ephemeral=True)
                    return
                else:
                    await db.tickets.update_one({"_id": existing["_id"]}, {"$set": {"status": "closed_manually"}})

            # 3. Load Config
            config = await db.ticket_config.find_one({"guild_id": interaction.guild.id}) or {}
            support_role_ids = config.get("support_role_ids", [])
            cat_id = config.get("ticket_category_id")
            
            # 4. Determine Category
            category = interaction.guild.get_channel(cat_id) if cat_id else None
            if not category:
                # Fallback logic
                category = discord.utils.get(interaction.guild.categories, name="Tickets")
                if not category:
                    try: 
                        category = await interaction.guild.create_category("Tickets") 
                    except discord.Forbidden:
                        await interaction.followup.send("❌ Немає прав на створення категорій!", ephemeral=True)
                        return

            # CHECK PERMISSIONS
            if not category.permissions_for(interaction.guild.me).manage_channels:
                 await interaction.followup.send(f"❌ У бота немає прав керувати каналами в категорії **{category.name}**!", ephemeral=True)
                 return

            # 5. Permission Overwrites
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
            }
            
            # Add support roles
            valid_roles = []
            for rid in support_role_ids:
                role = interaction.guild.get_role(rid)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
                    valid_roles.append(role)

            ticket_name = f"ticket-{interaction.user.name}"

            # 6. Create Channel with Timeout Safety
            try:
                # Використовуємо asyncio.wait_for, щоб не чекати вічно
                channel = await asyncio.wait_for(
                    interaction.guild.create_text_channel(
                        name=ticket_name,
                        category=category,
                        overwrites=overwrites
                    ),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                await interaction.followup.send("❌ Discord не відповів вчасно (тайм-аут). Спробуйте ще раз.", ephemeral=True)
                return
            except Exception as e:
                debug_log(f"Channel create error: {e}")
                await interaction.followup.send(f"❌ Помилка створення каналу: {e}", ephemeral=True)
                return

            # 7. DB Save
            await db.tickets.insert_one({
                "guild_id": interaction.guild.id,
                "channel_id": channel.id,
                "user_id": interaction.user.id,
                "created_at": datetime.now(),
                "status": "open"
            })

            # 8. Send Initial Message
            role_pings = " ".join([r.mention for r in valid_roles])
            embed = discord.Embed(
                title="Тікет відкрито",
                description=f"Привіт {interaction.user.mention}!\nОпишіть проблему. Підтримка скоро відповість.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            await channel.send(
                content=f"{interaction.user.mention} {role_pings}", 
                embed=embed, 
                view=TicketCloseView()
            )
            
            await interaction.followup.send(f"✅ Тікет створено: {channel.mention}", ephemeral=True)

        except Exception as e:
            log.error(f"Critical ticket error: {e}")
            await interaction.followup.send(f"❌ Критична помилка: {e}", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Закрити", style=discord.ButtonStyle.red, custom_id="ticket_btn_close", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await db.tickets.update_one(
                {"channel_id": interaction.channel_id}, 
                {"$set": {"status": "closed", "closed_at": datetime.now()}}
            )
            await interaction.channel.delete()
        except:
            pass

class TicketSystems(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketCloseView())
        self.bot.add_view(TicketConfigView())  # Register the config view too!

    @app_commands.command(name="ticket-setup", description="Налаштування системи тікетів (Ролі та Категорія)")
    async def ticket_setup(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Тільки для адміністраторів!", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="Налаштування Тікетів",
            description="Використовуйте меню нижче, щоб вибрати:\n1. **Ролі підтримки** (можна декілька)\n2. **Категорію** для нових тікетів",
            color=0x2b2d31
        )
        await interaction.response.send_message(embed=embed, view=TicketConfigView(), ephemeral=True)

    @app_commands.command(name="tickets", description="Створити кнопку для відкриття тікетів")
    @app_commands.describe(
        channel="Канал для публікації",
        title="Заголовок",
        description="Текст",
        button_label="Напис на кнопці",
        image_url="URL картинки"
    )
    async def tickets(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel,
        title: str = "Підтримка",
        description: str = "Натисніть кнопку, щоб відкрити тікет",
        button_label: str = "Відкрити тікет",
        image_url: str = None
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Тільки для адміністраторів!", ephemeral=True)
            return

        embed = discord.Embed(title=title, description=description, color=0x2b2d31)
        if image_url: 
            embed.set_image(url=image_url)
        embed.set_footer(text="Powered by bot")

        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(
            label=button_label, 
            style=discord.ButtonStyle.primary, 
            custom_id="ticket_btn_open", 
            emoji="🎫"
        )
        view.add_item(btn)

        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Панель створено в каналі {channel.mention}!\nНе забудьте налаштувати ролі через `/ticket-setup`.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystems(bot))
