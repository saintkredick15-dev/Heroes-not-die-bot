import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import traceback
import sys
from modules.db import get_database
from modules.logger import Logger

# Ініціалізація
db = get_database()
log = Logger("Tickets")

# --- DEBUG HELPER ---
def debug_log(message):
    """Виводить повідомлення в консоль для відладки."""
    print(f"[TICKET_DEBUG] {message}")
    sys.stdout.flush()

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label="Відкрити", style=discord.ButtonStyle.primary, custom_id="ticket_btn_open", emoji="🎫")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        debug_log(f"Button clicked by {interaction.user} in {interaction.guild}")
        await self.create_ticket(interaction)

    async def create_ticket(self, interaction: discord.Interaction):
        # 1. Defer interaction (важливо для уникнення тайм-аутів)
        try:
            await interaction.response.defer(ephemeral=True)
            debug_log("Interaction deferred successfully.")
        except Exception as e:
            debug_log(f"Failed to defer interaction: {e}")
            return

        try:
            # 2. Перевірка наявних тікетів
            debug_log("Checking for existing tickets...")
            existing_ticket = await db.tickets.find_one({
                "guild_id": interaction.guild.id,
                "user_id": interaction.user.id,
                "status": "open"
            })

            if existing_ticket:
                channel = interaction.guild.get_channel(existing_ticket["channel_id"])
                if channel:
                    await interaction.followup.send(f"⚠️ У вас вже є відкритий тікет: {channel.mention}", ephemeral=True)
                    return
                else:
                    debug_log("Existing ticket found in DB but channel missing. Closing in DB.")
                    await db.tickets.update_one(
                        {"_id": existing_ticket["_id"]},
                        {"$set": {"status": "closed_manually"}}
                    )

            # 3. Отримання конфігурації
            debug_log("Fetching guild configuration...")
            guild_config = await db.ticket_config.find_one({"guild_id": interaction.guild.id})
            
            support_role_ids = []
            ticket_category_id = None
            
            if guild_config:
                support_role_ids = guild_config.get("support_role_ids", [])
                ticket_category_id = guild_config.get("ticket_category_id")
                debug_log(f"Config found: CategoryID={ticket_category_id}, Roles={support_role_ids}")
            else:
                debug_log("No config found for this guild. Using defaults.")

            # 4. Визначення категорії
            category = None
            if ticket_category_id:
                category = interaction.guild.get_channel(ticket_category_id)
                if not category:
                    debug_log(f"Configured category {ticket_category_id} not found in guild.")
            
            if not category:
                # Шукаємо категорію за назвою або створюємо
                possible_names = ["Tickets", "Support", "Тікети", "Підтримка"]
                for name in possible_names:
                    category = discord.utils.get(interaction.guild.categories, name=name)
                    if category:
                        debug_log(f"Found fallback category: {category.name}")
                        break
                
                if not category:
                    debug_log("No category found. Creating new 'Tickets' category.")
                    try:
                        overwrites_cat = {
                            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                            interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
                        }
                        category = await interaction.guild.create_category("Tickets", overwrites=overwrites_cat)
                    except discord.Forbidden:
                        await interaction.followup.send("❌ Помилка: У бота немає прав створювати категорії!", ephemeral=True)
                        return
                    except Exception as e:
                        await interaction.followup.send(f"❌ Помилка при створенні категорії: {e}", ephemeral=True)
                        return

            # 5. Налаштування прав доступу
            debug_log("Setting up permissions...")
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }

            for role_id in support_role_ids:
                role = interaction.guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
                else:
                    debug_log(f"Role {role_id} not found in guild.")

            # 6. Створення каналу
            ticket_name = f"ticket-{interaction.user.name}"
            debug_log(f"Creating channel {ticket_name}...")
            
            try:
                channel = await interaction.guild.create_text_channel(
                    name=ticket_name,
                    category=category,
                    overwrites=overwrites
                )
            except discord.Forbidden:
                await interaction.followup.send("❌ Помилка: У бота немає прав керувати каналами!", ephemeral=True)
                return
            except Exception as e:
                debug_log(f"Channel creation failed: {e}")
                await interaction.followup.send(f"❌ Технічна помилка при створенні каналу: {e}", ephemeral=True)
                return

            # 7. Запис в БД
            try:
                await db.tickets.insert_one({
                    "guild_id": interaction.guild.id,
                    "channel_id": channel.id,
                    "user_id": interaction.user.id,
                    "created_at": datetime.now(),
                    "status": "open"
                })
            except Exception as e:
                debug_log(f"Database insert failed: {e}") 

            # 8. Відправка повідомлення в тікет
            mentions = [interaction.user.mention]
            for role_id in support_role_ids:
                role = interaction.guild.get_role(role_id)
                if role:
                    mentions.append(role.mention)
            
            mention_str = " ".join(mentions)

            embed = discord.Embed(
                title="Тікет відкрито",
                description=f"Привіт {interaction.user.mention}!\nОпишіть вашу проблему, модератори скоро зв'яжуться з вами.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.set_footer(text=f"Ticket ID: {channel.id}")
            
            close_view = TicketCloseView()
            await channel.send(content=mention_str, embed=embed, view=close_view)
            
            await interaction.followup.send(f"✅ Тікет успішно створено: {channel.mention}", ephemeral=True)
            debug_log("Ticket creation flow completed successfully.")

        except Exception as e:
            error_trace = traceback.format_exc()
            debug_log(f"CRITICAL ERROR: {error_trace}")
            log.error(f"Critical ticket error: {e}")
            await interaction.followup.send(f"❌ Критична помилка (повідомте розробнику):\n`{e}`", ephemeral=True)

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
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка при закритті: {e}", ephemeral=True)

class TicketSystems(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Реєструємо персистентні view
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketCloseView())
        debug_log("TicketViews registered.")

    @app_commands.command(name="tickets", description="Налаштувати та створити панель тікетів")
    @app_commands.describe(
        channel="Канал для відправки панелі",
        category="Категорія для нових тікетів",
        support_role1="Роль підтримки 1",
        support_role2="Роль підтримки 2",
        support_role3="Роль підтримки 3",
        title="Заголовок панелі",
        description="Текст панелі",
        button_label="Текст кнопки",
        image_url="URL картинки"
    )
    async def tickets(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel, 
        category: discord.CategoryChannel = None,
        support_role1: discord.Role = None,
        support_role2: discord.Role = None,
        support_role3: discord.Role = None,
        description: str = "Натисніть кнопку, щоб відкрити тікет",
        title: str = "Підтримка",
        button_label: str = "Відкрити тікет",
        image_url: str = None
    ):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("🚫 Тільки адміністратори можуть використовувати цю команду.", ephemeral=True)
            return

        try:
            # Збір налаштувань
            roles = []
            if support_role1: roles.append(support_role1.id)
            if support_role2: roles.append(support_role2.id)
            if support_role3: roles.append(support_role3.id)

            # Перевірка категорії
            cat_id_to_save = category.id if category else None

            # Збереження в БД
            update_data = {}
            if cat_id_to_save: update_data["ticket_category_id"] = cat_id_to_save
            if roles: update_data["support_role_ids"] = roles
            
            if update_data:
                await db.ticket_config.update_one(
                    {"guild_id": interaction.guild.id},
                    {"$set": update_data},
                    upsert=True
                )
                debug_log(f"Config updated for guild {interaction.guild.id}: {update_data}")

            # Embed
            embed = discord.Embed(title=title, description=description, color=0x2b2d31)
            embed.set_footer(text="System powered by bot")
            if image_url: embed.set_image(url=image_url)

            # Button
            view = discord.ui.View(timeout=None)
            button = discord.ui.Button(
                label=button_label,
                style=discord.ButtonStyle.primary,
                custom_id="ticket_btn_open",
                emoji="🎫"
            )
            view.add_item(button)

            await channel.send(embed=embed, view=view)
            
            msg = f"✅ Панель створено в {channel.mention}!"
            if category: msg += f"\n� Категорія: {category.name}"
            if roles: msg += f"\n👥 Ролі: " + ", ".join([f"<@&{r}>" for r in roles])
            
            await interaction.followup.send(msg, ephemeral=True)

        except Exception as e:
            debug_log(f"Setup error: {e}")
            await interaction.followup.send(f"❌ Помилка налаштування: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystems(bot))
