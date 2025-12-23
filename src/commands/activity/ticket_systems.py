import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import asyncio
import traceback
import sys
from modules.db import get_database
from modules.logger import Logger

# Ініціалізація
db = get_database()
log = Logger("Tickets")

# --- DEBUG HELPER ---
def debug_log(message):
    print(f"[TICKET_DEBUG] {message}")
    sys.stdout.flush()

# --- MODAL FOR PANEL TEXT ---
class TicketPanelModal(discord.ui.Modal, title="Налаштування Панелі"):
    panel_title = discord.ui.TextInput(
        label="Заголовок (Title)",
        placeholder="Підтримка Сервера",
        default="Відкрити тікет",
        max_length=256
    )
    panel_desc = discord.ui.TextInput(
        label="Опис (Description)",
        style=discord.TextStyle.paragraph,
        placeholder="Натисніть кнопку нижче...",
        default="Натисніть кнопку нижче, щоб зв'язатися з адміністрацією.",
        max_length=2000
    )
    btn_label = discord.ui.TextInput(
        label="Напис на кнопці",
        placeholder="Відкрити",
        default="Відкрити тікет",
        max_length=80
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            embed = discord.Embed(
                title=self.panel_title.value,
                description=self.panel_desc.value,
                color=0x2b2d31
            )
            embed.set_footer(text="Powered by Tickets v2")

            view = discord.ui.View(timeout=None)
            # ВАЖЛИВО: Новий custom_id "ticket_btn_open_v2", щоб старі кнопки не заважали
            btn = discord.ui.Button(
                label=self.btn_label.value,
                style=discord.ButtonStyle.primary,
                custom_id="ticket_btn_open_v2",
                emoji="🎫"
            )
            view.add_item(btn)

            await self.channel.send(embed=embed, view=view)
            await interaction.followup.send(f"✅ **Панель успішно опубліковано в каналі {self.channel.mention}!**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка публікації: {e}", ephemeral=True)

# --- DASHBOARD VIEW (ADMIN) ---
class TicketDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="1. Виберіть ролі підтримки (Admin/Mod)",
        min_values=0,
        max_values=20,
        custom_id="ticket_dash_roles",
        row=0
    )
    async def select_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await interaction.response.defer(ephemeral=True)
        try:
            role_ids = [role.id for role in select.values]
            await db.ticket_config.update_one(
                {"guild_id": interaction.guild.id},
                {"$set": {"support_role_ids": role_ids}},
                upsert=True
            )
            role_names = [role.name for role in select.values]
            await interaction.followup.send(f"✅ **Ролі збережено!**\nТепер доступ мають: {', '.join(role_names)}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка збереження ролей: {e}", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.category],
        placeholder="2. Виберіть категорію для тікетів",
        min_values=1,
        max_values=1,
        custom_id="ticket_dash_category",
        row=1
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer(ephemeral=True)
        try:
            category = select.values[0]
            await db.ticket_config.update_one(
                {"guild_id": interaction.guild.id},
                {"$set": {"ticket_category_id": category.id}},
                upsert=True
            )
            await interaction.followup.send(f"✅ **Категорія збережена!**\nТікети будуть тут: **{category.name}**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка збереження категорії: {e}", ephemeral=True)

    @discord.ui.button(label="3. Опублікувати Панель 📢", style=discord.ButtonStyle.green, row=2)
    async def publish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Відкриваємо модалку. Defer тут НЕ МОЖНА робити, бо modal - це відповідь на інтеракцію.
        # Тому просто await interaction.response.send_modal(...)
        await interaction.response.send_modal(TicketPanelModal(interaction.channel))

# --- PERSISTENT TICKET BUTTON LOGIC ---
class TicketViewV2(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(custom_id="ticket_btn_open_v2") # Label/Style не важливі тут, головне ID
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(interaction)

    async def create_ticket_logic(self, interaction: discord.Interaction):
        # 1. ЗАХИСТ ВІД ЗАВИСАННЯ
        try:
            await interaction.response.defer(ephemeral=True)
        except:
            return # Вже відповіли або тайм-аут

        try:
            # 2. Перевірка відкритих тікетів
            existing = await db.tickets.find_one({
                "guild_id": interaction.guild.id,
                "user_id": interaction.user.id,
                "status": "open"
            })
            if existing:
                channel = interaction.guild.get_channel(existing["channel_id"])
                if channel:
                    await interaction.followup.send(f"⚠️ У вас вже є тікет: {channel.mention}", ephemeral=True)
                    return
                else:
                    await db.tickets.update_one({"_id": existing["_id"]}, {"$set": {"status": "closed_manually"}})

            # 3. Завантаження налаштувань
            config = await db.ticket_config.find_one({"guild_id": interaction.guild.id}) or {}
            support_role_ids = config.get("support_role_ids", [])
            cat_id = config.get("ticket_category_id")

            # 4. Пошук категорії
            category = interaction.guild.get_channel(cat_id) if cat_id else None
            if not category:
                # Fallback: шукаємо по імені або створюємо
                category = discord.utils.get(interaction.guild.categories, name="Tickets")
                if not category:
                    try:
                        category = await interaction.guild.create_category("Tickets")
                    except discord.Forbidden:
                        await interaction.followup.send("❌ Бот не має прав створювати категорії!", ephemeral=True)
                        return

            # Перевірка прав бота в категорії
            if not category.permissions_for(interaction.guild.me).manage_channels:
                await interaction.followup.send(f"❌ Бот не має прав створювати канали в категорії **{category.name}**!", ephemeral=True)
                return

            # 5. Права доступу
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
            }
            
            # Додаємо ролі підтримки
            support_pings = []
            for rid in support_role_ids:
                role = interaction.guild.get_role(rid)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
                    support_pings.append(role.mention)
            
            # 6. Створення каналу (з тайм-аутом)
            ticket_name = f"ticket-{interaction.user.name}"
            # Обрізаємо ім'я, бо ліміт діскорда 100 символів, але краще менше
            ticket_name = ticket_name[:30].replace(" ", "-").lower()

            try:
                channel = await asyncio.wait_for(
                    interaction.guild.create_text_channel(name=ticket_name, category=category, overwrites=overwrites),
                    timeout=8.0
                )
            except asyncio.TimeoutError:
                await interaction.followup.send("❌ Discord не відповів вчасно (тайм-аут API). Спробуйте ще раз.", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"❌ Помилка створення каналу: {e}", ephemeral=True)
                return

            # 7. База даних
            await db.tickets.insert_one({
                "guild_id": interaction.guild.id,
                "channel_id": channel.id,
                "user_id": interaction.user.id,
                "created_at": datetime.now(),
                "status": "open"
            })

            # 8. Повідомлення в канал
            embed = discord.Embed(
                title="Тікет Відкрито",
                description=f"Привіт, {interaction.user.mention}!\nОпишіть вашу проблему. Підтримка відповість найближчим часом.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            pings = f"{interaction.user.mention} {' '.join(support_pings)}"
            await channel.send(content=pings, embed=embed, view=TicketCloseView())
            
            await interaction.followup.send(f"✅ Тікет створено: {channel.mention}", ephemeral=True)

        except Exception as e:
            log.error(f"Critical Ticket Error: {e}")
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

# --- MAIN COMMAND ---
class TicketSystems(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Реєструємо персистентну кнопку v2
        self.bot.add_view(TicketViewV2())
        self.bot.add_view(TicketCloseView())

    @app_commands.command(name="tickets", description="Відкрити Панель Керування Тікетами")
    async def tickets_dashboard(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Доступ заборонено (тільки Адміністратори).", ephemeral=True)
            return

        embed = discord.Embed(
            title="🛠️ Налаштування Тікетів",
            description=(
                "Використовуйте це меню для налаштування системи.\n\n"
                "1️⃣ **Виберіть Ролі**: Хто з адмінів буде бачити тікети.\n"
                "2️⃣ **Виберіть Категорію**: Де будуть створюватись канали.\n"
                "3️⃣ **Опублікувати**: Натисніть кнопку, щоб створити красиву панель у цьому каналі."
            ),
            color=0x2b2d31
        )
        # Відправляємо Dashboard View (він не мусить бути persistent, бо це налаштування)
        await interaction.response.send_message(embed=embed, view=TicketDashboardView(), ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystems(bot))
