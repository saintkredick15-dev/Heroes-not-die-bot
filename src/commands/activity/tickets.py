import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from modules.logger import Logger
from modules.db import get_database

log = Logger("Tickets")
db = get_database()
collection = db.ticket_config

async def get_config(guild_id: int):
    return await collection.find_one({"_id": guild_id}) or {}

async def update_config(guild_id: int, data: dict):
    await collection.update_one({"_id": guild_id}, {"$set": data}, upsert=True)

# --- Modals ---

class RoleInputModal(discord.ui.Modal, title="Додати роль за ID"):
    role_id = discord.ui.TextInput(label="ID ролі", placeholder="Наприклад: 123456789012345678")

    async def on_submit(self, interaction: discord.Interaction):
        raw_value = self.role_id.value.strip()
        try:
            r_id = int(raw_value)
            
            # Спроба отримати з кешу
            role = interaction.guild.get_role(r_id)
            
            # Якщо немає в кеші, пробуємо завантажити з API
            if not role:
                try:
                    role = await interaction.guild.fetch_role(r_id)
                except discord.NotFound:
                    role = None
                except discord.HTTPException:
                    role = None

            if not role:
                await interaction.response.send_message(f"❌ Роль з ID `{r_id}` не знайдена.\nПереконайтесь, що ви скопіювали правильний ID (Developer Mode -> Copy ID на ролі в налаштуваннях сервера).", ephemeral=True)
                return
            
            config = await get_config(interaction.guild.id)
            current_roles = config.get("support_role_ids", [])
            
            if r_id not in current_roles:
                current_roles.append(r_id)
                await update_config(interaction.guild.id, {"support_role_ids": current_roles})
                await interaction.response.send_message(f"✅ Роль {role.mention} успішно додано до списку підтримки.", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ Роль {role.mention} вже є в списку.", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message("❌ Невірний формат ID. ID має складатись лише з цифр.", ephemeral=True)

class PanelContentModal(discord.ui.Modal, title="Налаштування вмісту панелі"):
    panel_title = discord.ui.TextInput(label="Заголовок", placeholder="Служба підтримки", default="Служба підтримки")
    panel_desc = discord.ui.TextInput(label="Опис", style=discord.TextStyle.paragraph, placeholder="Натисніть кнопку, щоб створити тікет...", default="Натисніть кнопку нижче, щоб зв'язатися з адміністрацією.")
    
    def __init__(self, current_title, current_desc):
        super().__init__()
        self.panel_title.default = current_title
        self.panel_desc.default = current_desc

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

class ButtonConfigModal(discord.ui.Modal, title="Додати кнопку"):
    btn_label = discord.ui.TextInput(label="Текст кнопки", placeholder="Створити тікет")
    btn_emoji = discord.ui.TextInput(label="Emoji (необов'язково)", required=False, placeholder="🎫")
    
    def __init__(self, view_instance):
        super().__init__()
        self.view_instance = view_instance

    async def on_submit(self, interaction: discord.Interaction):
        # Валідація ліміту кнопок
        if len(self.view_instance.custom_buttons) >= 10:
            await interaction.response.send_message("❌ Максимум 10 кнопок!", ephemeral=True)
            return

        label = self.btn_label.value.strip() or "Тікет"
        emoji_str = self.btn_emoji.value.strip()
        emoji = None

        if emoji_str:
            try:
                # Спроба створити PartialEmoji щоб перевірити валідність
                if len(emoji_str) > 5 and emoji_str.startswith("<") and emoji_str.endswith(">"):
                     emoji = discord.PartialEmoji.from_str(emoji_str)
                else:
                     emoji = discord.PartialEmoji(name=emoji_str)
            except:
                await interaction.response.send_message(f"❌ Невірний формат емодзі: `{emoji_str}`. Будь ласка, використовуйте стандартні емодзі (😄) або Custom емодзі цього серверу.", ephemeral=True)
                return

        self.view_instance.custom_buttons.append({
            'label': label,
            'emoji': emoji_str if emoji_str else None,
            'style': discord.ButtonStyle.blurple 
        })
        await interaction.response.send_message(f"✅ Кнопка '{label}' додана!", ephemeral=True)

async def create_ticket_routine(interaction: discord.Interaction):
    guild = interaction.guild
    user = interaction.user

    # Дефер (відкладення), щоб уникнути "Interaction failed" при довгих операціях
    # Але оскільки ми посилаємо ефемерні відповіді, краще не деферити якщо ми плануємо send_message(ephemeral=True) зразу.
    # Тут логіка швидка, але краще обгорнути в try-except.

    config = await get_config(guild.id)
    
    # Category Logic
    category_id = config.get("category_id")
    category = guild.get_channel(category_id) if category_id else None
    
    if not category:
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            category = await guild.create_category("Tickets")

    channel_name = f"ticket-{user.name}".lower().replace(" ", "-")
    
    # Check existing
    existing_channel = discord.utils.get(guild.text_channels, name=channel_name, category_id=category.id)
    if existing_channel:
        await interaction.response.send_message(f"❌ У вас вже є відкритий тікет: {existing_channel.mention}", ephemeral=True)
        return

    # Permissions
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    
    # Support Roles
    support_role_ids = config.get("support_role_ids", [])
    for role_id in support_role_ids:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"User ID: {user.id}"
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка при створенні каналу: {e}", ephemeral=True)
        log.error(f"Failed to create ticket channel for {user}: {e}")
        return

    await interaction.response.send_message(f"✅ Тікет створено: {channel.mention}", ephemeral=True)

    embed = discord.Embed(
        title="Служба підтримки",
        description=f"Привіт {user.mention}! Опишіть вашу проблему, і адміністрація зв'яжеться з вами найближчим часом.",
        color=discord.Color.green()
    )
    
    await channel.send(embed=embed, view=TicketControlView())


class DynamicTicketView(discord.ui.View):
    def __init__(self, buttons_config):
        super().__init__(timeout=None)
        self.buttons_config = buttons_config
        self.add_dynamic_items()

    def add_dynamic_items(self):
        if not self.buttons_config:
             # Fallback default
             btn = discord.ui.Button(label="Створити тікет", style=discord.ButtonStyle.blurple, emoji="📩", custom_id="ticket_create_v2")
             btn.callback = self.ticket_callback
             self.add_item(btn)
        else:
            for btn_data in self.buttons_config:
                btn = discord.ui.Button(
                    label=btn_data['label'], 
                    emoji=btn_data['emoji'], 
                    style=btn_data['style'],
                    custom_id="ticket_create_v2" 
                )
                btn.callback = self.ticket_callback
                self.add_item(btn)

    async def ticket_callback(self, interaction: discord.Interaction):
        await create_ticket_routine(interaction)


class PanelBuilderView(discord.ui.View):
    def __init__(self, title, description):
        super().__init__(timeout=None)
        self.embed_title = title
        self.embed_desc = description
        self.custom_buttons = [] # List of dicts: {'label': str, 'emoji': str, 'style': ButtonStyle}

    def update_embed(self):
        title = self.embed_title or "Служба підтримки"
        desc = self.embed_desc or "Натисніть кнопку нижче."
        embed = discord.Embed(title=title, description=desc, color=discord.Color.blue())
        return embed

    @discord.ui.button(label="✏️ Редагувати текст", style=discord.ButtonStyle.primary)
    async def edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PanelContentModal(self.embed_title, self.embed_desc)
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        self.embed_title = modal.panel_title.value
        self.embed_desc = modal.panel_desc.value
        await interaction.edit_original_response(embed=self.update_embed())

    @discord.ui.button(label="➕ Додати кнопку", style=discord.ButtonStyle.secondary)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.custom_buttons) >= 10:
            await interaction.response.send_message("Максимум 10 кнопок!", ephemeral=True)
            return

        modal = ButtonConfigModal(self)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="✅ Надіслати панель", style=discord.ButtonStyle.success)
    async def send_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            final_view = DynamicTicketView(self.custom_buttons)
            await interaction.channel.send(embed=self.update_embed(), view=final_view)
            await interaction.response.edit_message(content="✅ Панель успішно створено!", embed=None, view=None)
        except Exception as e:
            await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)
            log.error(f"Panel error: {e}")


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Закрити тікет", style=discord.ButtonStyle.red, custom_id="ticket_close_v2")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Тікет буде закрито через 5 секунд...", ephemeral=True)
        await asyncio.sleep(5)
        await interaction.channel.delete()

class TicketConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.category], placeholder="Виберіть категорію для тікетів", min_values=0, max_values=1, custom_id="ticket_config_category")
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        category = select.values[0] if select.values else None
        category_id = category.id if category else None
        
        await update_config(interaction.guild.id, {"category_id": category_id})
        await interaction.response.send_message(f"Категорію встановлено: {category.mention if category else 'За замовчуванням'}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Виберіть ролі підтримки (max 20)", min_values=0, max_values=20, custom_id="ticket_config_roles")
    async def select_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role_ids = [role.id for role in select.values]
        await update_config(interaction.guild.id, {"support_role_ids": role_ids})
        roles_mentions = ", ".join([role.mention for role in select.values])
        await interaction.response.send_message(f"Список ролей перезаписано: {roles_mentions}", ephemeral=True)

    @discord.ui.button(label="➕ Додати роль (ID)", style=discord.ButtonStyle.green, custom_id="ticket_config_add_role_id")
    async def add_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RoleInputModal())

    @discord.ui.button(label="📋 Показати налаштування", style=discord.ButtonStyle.gray, custom_id="ticket_config_show")
    async def show_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await get_config(interaction.guild.id)
        
        cat_id = config.get("category_id")
        cat_mention = f"<#{cat_id}>" if cat_id else "Стандартна (Tickets)"
        
        role_ids = config.get("support_role_ids", [])
        roles_mentions = ", ".join([f"<@&{rid}>" for rid in role_ids])
        if not roles_mentions:
            roles_mentions = "Не налаштовано"
        
        embed = discord.Embed(title="Поточні налаштування", color=discord.Color.blue())
        embed.add_field(name="Категорія", value=cat_mention, inline=False)
        embed.add_field(name="Ролі підтримки", value=roles_mentions, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🗑️ Скинути налаштування", style=discord.ButtonStyle.red, custom_id="ticket_config_reset")
    async def reset_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Підтвердження
        confirm_view = discord.ui.View()
        confirm_view.add_item(discord.ui.Button(label="Так, скинути", style=discord.ButtonStyle.red, custom_id="confirm_reset"))
        
        async def confirm_callback(intx: discord.Interaction):
            await collection.delete_one({"_id": intx.guild.id})
            await intx.response.edit_message(content="✅ Налаштування скинуто до заводських.", view=None)
            
        confirm_view.children[0].callback = confirm_callback
        await interaction.response.send_message("Ви впевнені, що хочете видалити всі налаштування тікетів для цього сервера?", view=confirm_view, ephemeral=True)


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    # This acts as the listener for ANY button with custom_id="ticket_create_v2"
    # regardless of who sent it or what label it has.
    @discord.ui.button(label="Створити тікет", style=discord.ButtonStyle.blurple, emoji="📩", custom_id="ticket_create_v2")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket_routine(interaction)


class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketControlView())
        self.bot.add_view(TicketConfigView())
        log.info("Ticket views registered")

    tickets_group = discord.app_commands.Group(name="tickets", description="Керування системою тікетів")

    @tickets_group.command(name="setup", description="Швидке встановлення стандартної панелі")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        """Встановлює стандартну панель створення тікетів"""
        embed = discord.Embed(
            title="🎫 Створити тікет",
            description="Натисніть кнопку нижче, щоб зв'язатися з адміністрацією.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message("Панель створено!", ephemeral=True)
        await interaction.channel.send(embed=embed, view=TicketView())

    @tickets_group.command(name="settings", description="Налаштування системи тікетів (Категорія, Ролі)")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def settings(self, interaction: discord.Interaction):
        """Відкриває меню налаштувань"""
        embed = discord.Embed(
            title="⚙️ Налаштування Тікетів",
            description="Виберіть категорію для нових тікетів та ролі підтримки.\nВи можете додати роль зі списку або ввести її ID вручну.",
            color=discord.Color.light_grey()
        )
        await interaction.response.send_message(embed=embed, view=TicketConfigView(), ephemeral=True)

    @tickets_group.command(name="panel", description="Конструктор кастомної панелі тікетів")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def panel_builder(self, interaction: discord.Interaction):
        """Запускає конструктор панелі"""
        initial_title = "Служба підтримки"
        initial_desc = "Натисніть кнопку, щоб створити тікет."
        view = PanelBuilderView(initial_title, initial_desc)
        embed = view.update_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
