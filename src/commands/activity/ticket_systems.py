import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
import json
import math
from typing import Optional
from modules.db import get_database

db = get_database()

# Типи тікетів
TICKET_TYPES = {
    "role_application": {
        "name": "Заявка на роль",
        "description": "Подати заявку на отримання ролі",
        "emoji": "<:odym:1412519796456689714>",
        "questions": [
            "Чому ви хочете отримати цю роль?",
            "Чи маєте ви досвід, пов'язаний з цією роллю?",
            "Як ви плануєте використовувати цю роль?",
            "Додаткова інформація про себе:"
        ]
    },
    "server_suggestion": {
        "name": "Пропозиція для сервера",
        "description": "Поділитися ідеями для покращення сервера",
        "emoji": "<:dva:1412519805185163274>",
        "questions": [
            "Яка ваша пропозиція?",
            "Як це покращить сервер?",
            "Чи розглядали ви можливі недоліки?",
            "Додаткові деталі або коментарі:"
        ]
    },
    "bug_report": {
        "name": "Звіт про баг",
        "description": "Повідомити про технічні проблеми",
        "emoji": "<:try:1412519816245547038>",
        "questions": [
            "Опишіть проблему детально:",
            "Як відтворити цю помилку?",
            "Що ви очікували побачити?",
            "Додаткова інформація (скріншоти, логи):"
        ]
    },
    "general_support": {
        "name": "Загальна підтримка",
        "description": "Питання або допомога від модерації",
        "emoji": "<:chetyri:1412519826274127973>",
        "questions": [
            "Опишіть ваше питання або проблему:",
            "Чи намагались ви вирішити це самостійно?",
            "Додаткові деталі:"
        ]
    },
    "complaint": {
        "name": "Скарга",
        "description": "Подати скаргу на користувача або ситуацію",
        "emoji": "<:pyat:1412519858960339064>",
        "questions": [
            "На кого або що ви скаржитесь?",
            "Що сталося? Опишіть ситуацію:",
            "Чи є у вас докази (скріншоти, повідомлення)?",
            "Додаткова інформація:"
        ]
    }
}

# Утилітні функції
async def get_guild_config(guild_id: int):
    config = await db.ticket_config.find_one({"guild_id": guild_id})
    if not config:
        default_config = {
            "guild_id": guild_id,
            "moderator_role_ids": [],
            "category_id": None,
            "log_channel_id": None,
            "available_roles": []
        }
        await db.ticket_config.insert_one(default_config)
        return default_config
    
    # Міграція старого формату
    if "moderator_role_id" in config and "moderator_role_ids" not in config:
        moderator_role_ids = [config["moderator_role_id"]] if config.get("moderator_role_id") else []
        config["moderator_role_ids"] = moderator_role_ids
        await db.ticket_config.update_one(
            {"guild_id": guild_id},
            {"$set": {"moderator_role_ids": moderator_role_ids}, "$unset": {"moderator_role_id": ""}}
        )
    
    return config

async def update_guild_config(guild_id: int, updates: dict):
    await db.ticket_config.update_one(
        {"guild_id": guild_id},
        {"$set": updates},
        upsert=True
    )

async def save_ticket_stat(guild_id: int):
    today = datetime.now().strftime('%Y-%m-%d')
    await db.ticket_stats.update_one(
        {"guild_id": guild_id, "date": today},
        {"$inc": {"count": 1}},
        upsert=True
    )

async def get_week_stats(guild_id: int):
    stats = []
    for i in range(7):
        date = (datetime.now() - timedelta(days=6-i)).strftime('%Y-%m-%d')
        stat = await db.ticket_stats.find_one({"guild_id": guild_id, "date": date})
        count = stat["count"] if stat else 0
        stats.append((date, count))
    return stats

def has_moderator_permissions(interaction: discord.Interaction, guild_config: dict) -> bool:
    """Перевіряє чи має користувач права модератора"""
    if not guild_config.get("moderator_role_ids"):
        return interaction.user.guild_permissions.administrator
    return any(role.id in guild_config["moderator_role_ids"] for role in interaction.user.roles)

async def send_dm_notification(user: discord.Member, embed: discord.Embed):
    """Відправляє DM користувачу"""
    try:
        await user.send(embed=embed)
    except:
        pass

async def log_ticket_action(guild: discord.Guild, guild_config: dict, embed: discord.Embed):
    """Логування дій з тікетами"""
    if not guild_config.get("log_channel_id"):
        return
    log_channel = guild.get_channel(guild_config["log_channel_id"])
    if log_channel:
        try:
            await log_channel.send(embed=embed)
        except:
            pass

# Нові класи для пагінації ролей
class RolesPaginationView(discord.ui.View):
    def __init__(self, guild: discord.Guild, guild_config: dict, mode: str, page: int = 0):
        super().__init__(timeout=600)
        self.guild = guild
        self.guild_config = guild_config
        self.mode = mode  # "ticket_roles" or "moderator_roles"
        self.page = page
        self.selected_roles = set()
        
        # Отримуємо всі ролі
        if mode == "ticket_roles":
            # Для тікет ролей показуємо всі ролі крім @everyone, ботів та інтеграцій
            self.all_roles = [
                role for role in guild.roles 
                if not role.is_default() and not role.is_bot_managed() and not role.is_integration()
            ]
        else:  # moderator_roles
            # Для модераторських ролей показуємо всі ролі крім @everyone
            self.all_roles = [role for role in guild.roles if not role.is_default()]
        
        # Сортуємо за позицією (найвищі ролі спочатку)
        self.all_roles.sort(key=lambda r: r.position, reverse=True)
        
        self.roles_per_page = 20
        self.total_pages = math.ceil(len(self.all_roles) / self.roles_per_page)
        
        self.update_view()
    
    def get_page_roles(self):
        start = self.page * self.roles_per_page
        end = start + self.roles_per_page
        return self.all_roles[start:end]
    
    def update_view(self):
        self.clear_items()
        
        # Додаємо селект меню з ролями поточної сторінки
        page_roles = self.get_page_roles()
        if page_roles:
            options = []
            for role in page_roles:
                # Перевіряємо чи роль вже додана
                if self.mode == "ticket_roles":
                    is_selected = role.id in self.guild_config.get("available_roles", [])
                else:
                    is_selected = role.id in self.guild_config.get("moderator_role_ids", [])
                
                # Перевіряємо чи роль вибрана в поточній сесії
                session_selected = role.id in self.selected_roles
                
                label = role.name
                if len(label) > 100:
                    label = label[:97] + "..."
                
                description = f"Позиція: {role.position}"
                if is_selected:
                    description += " • Вже додана"
                elif session_selected:
                    description += " • Обрана"
                
                options.append(discord.SelectOption(
                    label=label,
                    value=str(role.id),
                    description=description,
                    emoji="✅" if session_selected else ("🔹" if is_selected else None)
                ))
            
            role_select = RolePageSelect(self.mode, options)
            role_select.parent_view = self
            self.add_item(role_select)
        
        # Кнопки навігації
        if self.total_pages > 1:
            # Попередня сторінка
            prev_button = discord.ui.Button(
                label="◀️ Попередня",
                style=discord.ButtonStyle.secondary,
                disabled=self.page == 0
            )
            prev_button.callback = self.prev_page
            self.add_item(prev_button)
            
            # Наступна сторінка
            next_button = discord.ui.Button(
                label="Наступна ▶️",
                style=discord.ButtonStyle.secondary,
                disabled=self.page >= self.total_pages - 1
            )
            next_button.callback = self.next_page
            self.add_item(next_button)
        
        # Кнопки дій
        if self.selected_roles:
            save_button = discord.ui.Button(
                label=f"Зберегти зміни ({len(self.selected_roles)})",
                style=discord.ButtonStyle.green,
                emoji="💾"
            )
            save_button.callback = self.save_changes
            self.add_item(save_button)
        
        clear_button = discord.ui.Button(
            label="Очистити вибір",
            style=discord.ButtonStyle.secondary,
            emoji="🗑️",
            disabled=not self.selected_roles
        )
        clear_button.callback = self.clear_selection
        self.add_item(clear_button)
        
        cancel_button = discord.ui.Button(
            label="Скасувати",
            style=discord.ButtonStyle.red,
            emoji="❌"
        )
        cancel_button.callback = self.cancel
        self.add_item(cancel_button)
    
    async def prev_page(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self.update_view()
        await self.update_message(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        self.page = min(self.total_pages - 1, self.page + 1)
        self.update_view()
        await self.update_message(interaction)
    
    async def save_changes(self, interaction: discord.Interaction):
        if self.mode == "ticket_roles":
            current_roles = set(self.guild_config.get("available_roles", []))
            new_roles = list(current_roles | self.selected_roles)  # Об'єднуємо множини
            await update_guild_config(self.guild.id, {"available_roles": new_roles})
            
            added_roles = [self.guild.get_role(role_id) for role_id in self.selected_roles]
            added_roles = [role for role in added_roles if role]
            
            embed = discord.Embed(
                title="Ролі для тікетів оновлено",
                description=f"Додано {len(added_roles)} ролей",
                color=0x57f287
            )
            
            if added_roles:
                role_list = [f"+ {role.mention}" for role in added_roles]
                embed.add_field(
                    name="Додані ролі",
                    value="\n".join(role_list[:10]) + (f"\n... та ще {len(role_list) - 10}" if len(role_list) > 10 else ""),
                    inline=False
                )
            
            embed.add_field(
                name="Загальна кількість",
                value=f"{len(new_roles)} ролей доступно для заявок",
                inline=True
            )
        
        else:  # moderator_roles
            current_roles = set(self.guild_config.get("moderator_role_ids", []))
            new_roles = list(current_roles | self.selected_roles)  # Об'єднуємо множини
            await update_guild_config(self.guild.id, {"moderator_role_ids": new_roles})
            
            added_roles = [self.guild.get_role(role_id) for role_id in self.selected_roles]
            added_roles = [role for role in added_roles if role]
            
            embed = discord.Embed(
                title="Модераторські ролі оновлено",
                description=f"Додано {len(added_roles)} ролей",
                color=0x57f287
            )
            
            if added_roles:
                role_list = [f"+ {role.mention}" for role in added_roles]
                embed.add_field(
                    name="Додані ролі",
                    value="\n".join(role_list[:10]) + (f"\n... та ще {len(role_list) - 10}" if len(role_list) > 10 else ""),
                    inline=False
                )
            
            embed.add_field(
                name="Загальна кількість",
                value=f"{len(new_roles)} модераторських ролей",
                inline=True
            )
        
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def clear_selection(self, interaction: discord.Interaction):
        self.selected_roles.clear()
        self.update_view()
        await self.update_message(interaction)
    
    async def cancel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Налаштування скасовано",
            description="Зміни не збережено",
            color=0xfee75c
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def update_message(self, interaction: discord.Interaction):
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_embed(self):
        if self.mode == "ticket_roles":
            title = "Налаштування ролей для тікетів"
            description = "Оберіть ролі, на які користувачі можуть подавати заявки"
        else:
            title = "Налаштування модераторських ролей"
            description = "Оберіть ролі, які можуть керувати тікетами"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=0x2b2d31
        )
        
        embed.add_field(
            name="Сторінка",
            value=f"{self.page + 1}/{self.total_pages}",
            inline=True
        )
        
        embed.add_field(
            name="Всього ролей",
            value=f"{len(self.all_roles)}",
            inline=True
        )
        
        embed.add_field(
            name="Обрано зараз",
            value=f"{len(self.selected_roles)}",
            inline=True
        )
        
        if self.selected_roles:
            selected_roles_list = []
            for role_id in list(self.selected_roles)[:5]:  # Показуємо перші 5
                role = self.guild.get_role(role_id)
                if role:
                    selected_roles_list.append(role.name)
            
            selected_text = "\n".join(selected_roles_list)
            if len(self.selected_roles) > 5:
                selected_text += f"\n... та ще {len(self.selected_roles) - 5}"
            
            embed.add_field(
                name="Обрані ролі",
                value=selected_text,
                inline=False
            )
        
        embed.set_footer(text="Оберіть ролі зі списку нижче")
        return embed

class RolePageSelect(discord.ui.Select):
    def __init__(self, mode: str, options: list):
        self.mode = mode
        self.parent_view = None
        super().__init__(
            placeholder="Оберіть ролі для додавання/видалення...",
            options=options,
            min_values=0,
            max_values=len(options)
        )
    
    async def callback(self, interaction: discord.Interaction):
        for value in self.values:
            role_id = int(value)
            if role_id in self.parent_view.selected_roles:
                self.parent_view.selected_roles.discard(role_id)  # Видаляємо якщо вже є
            else:
                self.parent_view.selected_roles.add(role_id)  # Додаємо якщо немає
        
        self.parent_view.update_view()
        embed = self.parent_view.create_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class RemoveRolesView(discord.ui.View):
    def __init__(self, guild: discord.Guild, guild_config: dict, mode: str):
        super().__init__(timeout=600)
        self.guild = guild
        self.guild_config = guild_config
        self.mode = mode
        self.selected_roles = set()
        
        # Отримуємо поточні ролі
        if mode == "ticket_roles":
            role_ids = guild_config.get("available_roles", [])
        else:
            role_ids = guild_config.get("moderator_role_ids", [])
        
        self.current_roles = []
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role:
                self.current_roles.append(role)
        
        self.current_roles.sort(key=lambda r: r.position, reverse=True)
        
        self.update_view()
    
    def update_view(self):
        self.clear_items()
        
        if not self.current_roles:
            return
        
        # Створюємо опції для видалення
        options = []
        for role in self.current_roles:
            label = role.name
            if len(label) > 100:
                label = label[:97] + "..."
            
            description = f"Позиція: {role.position}"
            if role.id in self.selected_roles:
                description += " • Обрана для видалення"
            
            options.append(discord.SelectOption(
                label=label,
                value=str(role.id),
                description=description,
                emoji="❌" if role.id in self.selected_roles else "🔹"
            ))
        
        # Розбиваємо на групи по 25
        for i in range(0, len(options), 25):
            chunk_options = options[i:i+25]
            remove_select = RemoveRoleSelect(self.mode, chunk_options)
            remove_select.parent_view = self
            self.add_item(remove_select)
        
        # Кнопки дій
        if self.selected_roles:
            remove_button = discord.ui.Button(
                label=f"Видалити обрані ({len(self.selected_roles)})",
                style=discord.ButtonStyle.red,
                emoji="🗑️"
            )
            remove_button.callback = self.remove_selected
            self.add_item(remove_button)
        
        cancel_button = discord.ui.Button(
            label="Скасувати",
            style=discord.ButtonStyle.secondary,
            emoji="❌"
        )
        cancel_button.callback = self.cancel
        self.add_item(cancel_button)
    
    async def remove_selected(self, interaction: discord.Interaction):
        if self.mode == "ticket_roles":
            current_roles = set(self.guild_config.get("available_roles", []))
            new_roles = list(current_roles - self.selected_roles)
            await update_guild_config(self.guild.id, {"available_roles": new_roles})
            
            removed_roles = [self.guild.get_role(role_id) for role_id in self.selected_roles]
            removed_roles = [role for role in removed_roles if role]
            
            embed = discord.Embed(
                title="Ролі видалено",
                description=f"Видалено {len(removed_roles)} ролей з тікетів",
                color=0xed4245
            )
            
            if removed_roles:
                role_list = [f"- {role.mention}" for role in removed_roles]
                embed.add_field(
                    name="Видалені ролі",
                    value="\n".join(role_list[:10]) + (f"\n... та ще {len(role_list) - 10}" if len(role_list) > 10 else ""),
                    inline=False
                )
            
            embed.add_field(
                name="Залишилось ролей",
                value=f"{len(new_roles)} ролей",
                inline=True
            )
        
        else:  # moderator_roles
            current_roles = set(self.guild_config.get("moderator_role_ids", []))
            new_roles = list(current_roles - self.selected_roles)
            await update_guild_config(self.guild.id, {"moderator_role_ids": new_roles})
            
            removed_roles = [self.guild.get_role(role_id) for role_id in self.selected_roles]
            removed_roles = [role for role in removed_roles if role]
            
            embed = discord.Embed(
                title="Модераторські ролі видалено",
                description=f"Видалено {len(removed_roles)} ролей",
                color=0xed4245
            )
            
            if removed_roles:
                role_list = [f"- {role.mention}" for role in removed_roles]
                embed.add_field(
                    name="Видалені ролі",
                    value="\n".join(role_list[:10]) + (f"\n... та ще {len(role_list) - 10}" if len(role_list) > 10 else ""),
                    inline=False
                )
            
            embed.add_field(
                name="Залишилось ролей",
                value=f"{len(new_roles)} ролей",
                inline=True
            )
        
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def cancel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Видалення скасовано",
            description="Ролі не змінено",
            color=0xfee75c
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    def create_embed(self):
        if self.mode == "ticket_roles":
            title = "Видалення ролей з тікетів"
            description = "Оберіть ролі для видалення"
        else:
            title = "Видалення модераторських ролей"
            description = "Оберіть ролі для видалення"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=0xed4245
        )
        
        embed.add_field(
            name="Всього ролей",
            value=f"{len(self.current_roles)}",
            inline=True
        )
        
        embed.add_field(
            name="Обрано для видалення",
            value=f"{len(self.selected_roles)}",
            inline=True
        )
        
        return embed

class RemoveRoleSelect(discord.ui.Select):
    def __init__(self, mode: str, options: list):
        self.mode = mode
        self.parent_view = None
        super().__init__(
            placeholder="Оберіть ролі для видалення...",
            options=options,
            min_values=0,
            max_values=len(options)
        )
    
    async def callback(self, interaction: discord.Interaction):
        for value in self.values:
            role_id = int(value)
            if role_id in self.parent_view.selected_roles:
                self.parent_view.selected_roles.discard(role_id)
            else:
                self.parent_view.selected_roles.add(role_id)
        
        self.parent_view.update_view()
        embed = self.parent_view.create_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

# Залишаємо всі попередні класи без змін
class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for ticket_type, config in TICKET_TYPES.items():
            options.append(
                discord.SelectOption(
                    label=config["name"],
                    description=config["description"], 
                    value=ticket_type,
                    emoji=config["emoji"]
                )
            )
        
        super().__init__(
            placeholder="Оберіть тип тікета...",
            options=options,
            custom_id="ticket_type_select_main"
        )
    
    async def callback(self, interaction: discord.Interaction):
        ticket_type = self.values[0]
        guild_config = await get_guild_config(interaction.guild.id)
        
        if ticket_type == "role_application":
            if not guild_config["available_roles"]:
                await interaction.response.send_message(
                    "Адміністратори ще не налаштували доступні ролі для заявок.", 
                    ephemeral=True
                )
                return
            
            available_roles = [interaction.guild.get_role(role_id) 
                             for role_id in guild_config["available_roles"]]
            available_roles = [role for role in available_roles if role and not role.is_bot_managed()]
            
            if not available_roles:
                await interaction.response.send_message(
                    "Всі налаштовані ролі недоступні або видалені.", 
                    ephemeral=True
                )
                return
            
            view = RoleSelectView(interaction.guild, available_roles)
            embed = discord.Embed(
                title="Заявка на роль",
                description="Оберіть роль, на яку хочете подати заявку:",
                color=0x2b2d31
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await self.create_ticket(interaction, ticket_type)
    
    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str, role_id: int = None):
        config = TICKET_TYPES[ticket_type]
        guild_config = await get_guild_config(interaction.guild.id)
        
        # Перевіряємо чи вже є відкритий тікет
        existing_ticket = await db.tickets.find_one({
            "guild_id": interaction.guild.id,
            "user_id": interaction.user.id,
            "ticket_type": ticket_type,
            "status": "open"
        })
        
        if existing_ticket:
            channel = interaction.guild.get_channel(existing_ticket["channel_id"])
            if channel:
                await interaction.response.send_message(
                    f"У вас вже є відкритий тікет: {channel.mention}",
                    ephemeral=True
                )
                return
        
        # Створення каналу
        category = await self.get_or_create_category(interaction.guild, guild_config)
        if not category:
            await interaction.response.send_message(
                "Не вдалося створити категорію для тікетів", 
                ephemeral=True
            )
            return
        
        # Назва тікета (спрощена)
        if role_id:
            role = interaction.guild.get_role(role_id)
            ticket_name = f"роль-{role.name if role else 'unknown'}"
        else:
            config_name = config['name'].lower().replace(' ', '-')
            ticket_name = config_name
        
        ticket_name = f"{ticket_name}-{interaction.user.id}"[:50]
        
        # Права доступу
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True, embed_links=True
            ),
        }
        
        # Додаємо всі ролі модераторів
        for mod_role_id in guild_config["moderator_role_ids"]:
            mod_role = interaction.guild.get_role(mod_role_id)
            if mod_role:
                overwrites[mod_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, manage_messages=True,
                    attach_files=True, embed_links=True
                )
        
        try:
            channel = await category.create_text_channel(
                name=ticket_name.lower().replace(" ", "-"),
                overwrites=overwrites
            )
            
            # Збереження в базу
            ticket_data = {
                "guild_id": interaction.guild.id,
                "channel_id": channel.id,
                "user_id": interaction.user.id,
                "ticket_type": ticket_type,
                "role_id": role_id,
                "created_at": datetime.now(),
                "status": "open"
            }
            await db.tickets.insert_one(ticket_data)
            
            # Основне повідомлення
            embed = discord.Embed(
                title=f"{config['name']}",
                description=f"**Користувач:** {interaction.user.mention}\n**Створено:** <t:{int(datetime.now().timestamp())}:F>",
                color=0x2b2d31,
                timestamp=datetime.now()
            )
            
            if role_id:
                role = interaction.guild.get_role(role_id)
                embed.add_field(
                    name="Запитувана роль",
                    value=f"{role.mention if role else 'Невідома роль'}",
                    inline=True
                )
            
            embed.set_footer(text=f"ID користувача: {interaction.user.id}")
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            # Вибір view
            if ticket_type == "role_application":
                view = RoleApplicationButtons(role_id, interaction.user.id, channel.id)
            else:
                view = GeneralTicketButtons(ticket_type, interaction.user.id, channel.id)
            
            # Формуємо повідомлення з упоминаннями модераторів
            mentions = [interaction.user.mention]
            for mod_role_id in guild_config["moderator_role_ids"]:
                mod_role = interaction.guild.get_role(mod_role_id)
                if mod_role:
                    mentions.append(mod_role.mention)
            
            mention_text = " | ".join(mentions)
            
            # Відправлення повідомлення
            await channel.send(mention_text, embed=embed, view=view)
            
            # Питання
            await self.ask_questions(channel, config['questions'])
            
            # Статистика
            await save_ticket_stat(interaction.guild.id)
            
            # Відповідь користувачу
            success_embed = discord.Embed(
                title="Тікет успішно створено",
                description=f"**Ваш тікет:** {channel.mention}\n\n" +
                           f"Тип: {config['name']}\n" +
                           f"Очікуйте відповіді від модерації",
                color=0x57f287
            )
            
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=success_embed, view=None)
            else:
                await interaction.response.send_message(embed=success_embed, view=None, ephemeral=True)
            
            # Лог
            log_embed = discord.Embed(
                title="Новий тікет створено",
                color=0x2b2d31,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Користувач", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
            log_embed.add_field(name="Тип", value=config['name'], inline=True)
            log_embed.add_field(name="Канал", value=channel.mention, inline=True)
            log_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await log_ticket_action(interaction.guild, guild_config, log_embed)
            
        except Exception as e:
            error_message = f"Помилка створення тікета: {e}"
            if interaction.response.is_done():
                await interaction.edit_original_response(content=error_message, embed=None, view=None)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)
    
    async def get_or_create_category(self, guild: discord.Guild, guild_config: dict):
        """Знаходить або створює категорію для тікетів"""
        if guild_config["category_id"]:
            category = guild.get_channel(guild_config["category_id"])
            if category:
                return category
        
        for cat in guild.categories:
            if cat.name.lower() in ["tickets", "тікети", "тикеты"]:
                await update_guild_config(guild.id, {"category_id": cat.id})
                return cat
        
        try:
            category = await guild.create_category("Тікети")
            await update_guild_config(guild.id, {"category_id": category.id})
            return category
        except:
            return None
    
    async def ask_questions(self, channel: discord.TextChannel, questions: list):
        """Задає питання користувачу"""
        await asyncio.sleep(3)
        
        questions_embed = discord.Embed(
            title="Анкета",
            description="Будь ласка, дайте відповіді на наступні питання:",
            color=0x2b2d31
        )
        
        for i, question in enumerate(questions, 1):
            questions_embed.add_field(
                name=f"Питання {i}",
                value=question,
                inline=False
            )
        
        await channel.send(embed=questions_embed)

class RoleSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild, available_roles: list):
        super().__init__(timeout=600)
        
        options = []
        available_roles.sort(key=lambda r: r.position, reverse=True)
        
        for role in available_roles[:25]:
            options.append(
                discord.SelectOption(
                    label=role.name,
                    description=f"Подати заявку на роль {role.name}",
                    value=str(role.id)
                )
            )
        
        select = discord.ui.Select(
            placeholder="Оберіть роль...",
            options=options
        )
        
        async def select_callback(select_interaction):
            role_id = int(select.values[0])
            role = select_interaction.guild.get_role(role_id)
            
            if not role or role in select_interaction.user.roles:
                await select_interaction.response.send_message(
                    f"{'Роль не знайдена!' if not role else f'У вас вже є роль {role.mention}!'}", 
                    ephemeral=True
                )
                return
            
            ticket_select = TicketTypeSelect()
            await ticket_select.create_ticket(select_interaction, "role_application", role_id)
        
        select.callback = select_callback
        self.add_item(select)

class RejectModal(discord.ui.Modal, title="Причина відхилення"):
    def __init__(self, role_id: int, user_id: int, channel_id: int):
        super().__init__(timeout=300)
        self.role_id = role_id
        self.user_id = user_id
        self.channel_id = channel_id
    
    reason = discord.ui.TextInput(
        label="Причина відхилення заявки",
        placeholder="Вкажіть чому заявку було відхилено...",
        required=True,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.guild.get_member(self.user_id)
        role = interaction.guild.get_role(self.role_id)
        
        await db.tickets.update_one(
            {"channel_id": self.channel_id},
            {"$set": {
                "status": "rejected", 
                "rejected_by": interaction.user.id, 
                "rejected_at": datetime.now(),
                "reject_reason": self.reason.value
            }}
        )
        
        embed = discord.Embed(
            title="Заявку відхилено",
            description=f"**Користувач:** {user.mention if user else 'Користувач покинув сервер'}\n" +
                       f"**Роль:** {role.mention if role else 'Роль видалена'}\n" +
                       f"**Модератор:** {interaction.user.mention}",
            color=0xed4245,
            timestamp=datetime.now()
        )
        embed.add_field(name="Причина відхилення", value=self.reason.value, inline=False)
        
        await interaction.response.edit_message(embed=embed, view=TicketCloseView())
        
        # DM користувачу
        if user:
            dm_embed = discord.Embed(
                title="<:palka:1412777364387135589> Заявку відхилено",
                description=f"На жаль, вашу заявку на роль **{role.name if role else 'невідома роль'}** відхилено.\n\n" +
                           f"**Сервер:** {interaction.guild.name}\n" +
                           f"**Причина:** {self.reason.value}\n\n" +
                           f"Ви можете подати нову заявку пізніше",
                color=0xed4245,
                timestamp=datetime.now()
            )
            await send_dm_notification(user, dm_embed)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Закрити тікет", style=discord.ButtonStyle.secondary, custom_id="close_ticket_final")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_config = await get_guild_config(interaction.guild.id)
        
        if not has_moderator_permissions(interaction, guild_config):
            await interaction.response.send_message("Недостатньо прав!", ephemeral=True)
            return
        
        await db.tickets.update_one(
            {"channel_id": interaction.channel.id},
            {"$set": {"status": "closed", "closed_by": interaction.user.id, "closed_at": datetime.now()}}
        )
        
        embed = discord.Embed(
            title="Тікет закривається",
            description=f"Тікет закрито модератором {interaction.user.mention}\n\n" +
                       f"Час закриття: <t:{int(datetime.now().timestamp())}:F>\n" +
                       f"Канал буде видалено через 15 секунд...",
            color=0xfee75c,
            timestamp=datetime.now()
        )
        embed.set_footer(text="Дякуємо за використання системи тікетів")
        
        await interaction.response.edit_message(embed=embed, view=None)
        
        # Лог
        log_embed = discord.Embed(
            title="Тікет закрито",
            color=0xfee75c,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Канал", value=f"#{interaction.channel.name}", inline=True)
        log_embed.add_field(name="Модератор", value=interaction.user.mention, inline=True)
        await log_ticket_action(interaction.guild, guild_config, log_embed)
        
        await asyncio.sleep(15)
        try:
            await interaction.channel.delete(reason=f"Тікет закрито модератором {interaction.user}")
        except:
            pass

class RoleApplicationButtons(discord.ui.View):
    def __init__(self, role_id: int = None, user_id: int = None, channel_id: int = None):
        super().__init__(timeout=None)
        self.role_id = role_id
        self.user_id = user_id
        self.channel_id = channel_id
    
    @discord.ui.button(label="Схвалити заявку", style=discord.ButtonStyle.green, custom_id="approve_role_application")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_config = await get_guild_config(interaction.guild.id)
        
        if not has_moderator_permissions(interaction, guild_config):
            await interaction.response.send_message("Недостатньо прав!", ephemeral=True)
            return
        
        # Отримуємо дані з бази якщо потрібно
        if not all([self.role_id, self.user_id]):
            ticket_data = await db.tickets.find_one({"channel_id": interaction.channel.id})
            if ticket_data:
                self.role_id = ticket_data.get("role_id")
                self.user_id = ticket_data.get("user_id")
        
        user = interaction.guild.get_member(self.user_id)
        role = interaction.guild.get_role(self.role_id)
        
        if not user or not role:
            await interaction.response.send_message("Користувач або роль не знайдені!", ephemeral=True)
            return
        
        try:
            await user.add_roles(role, reason=f"Схвалено модератором {interaction.user}")
            
            await db.tickets.update_one(
                {"channel_id": interaction.channel.id},
                {"$set": {"status": "approved", "approved_by": interaction.user.id, "approved_at": datetime.now()}}
            )
            
            embed = discord.Embed(
                title="Заявку схвалено",
                description=f"**Користувач:** {user.mention}\n**Роль:** {role.mention}\n**Модератор:** {interaction.user.mention}",
                color=0x57f287,
                timestamp=datetime.now()
            )
            embed.add_field(
                name="Вітаємо",
                value=f"Роль **{role.name}** успішно додано до профілю користувача",
                inline=False
            )
            
            await interaction.response.edit_message(embed=embed, view=TicketCloseView())
            
            # DM користувачу
            dm_embed = discord.Embed(
                title="<:palka:1412777364387135589> Заявку схвалено",
                description=f"Вашу заявку на роль **{role.name}** схвалено\n\n" +
                           f"**Сервер:** {interaction.guild.name}\n" +
                           f"**Модератор:** {interaction.user.mention}\n\n" +
                           f"Роль додано до вашого профілю",
                color=0x57f287,
                timestamp=datetime.now()
            )
            await send_dm_notification(user, dm_embed)
            
        except Exception as e:
            await interaction.response.send_message(f"Помилка додавання ролі: {e}", ephemeral=True)
    
    @discord.ui.button(label="Відхилити заявку", style=discord.ButtonStyle.red, custom_id="reject_role_application")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_config = await get_guild_config(interaction.guild.id)
        
        if not has_moderator_permissions(interaction, guild_config):
            await interaction.response.send_message("Недостатньо прав!", ephemeral=True)
            return
        
        if not all([self.role_id, self.user_id]):
            ticket_data = await db.tickets.find_one({"channel_id": interaction.channel.id})
            if ticket_data:
                self.role_id = ticket_data.get("role_id")
                self.user_id = ticket_data.get("user_id")
        
        modal = RejectModal(self.role_id, self.user_id, interaction.channel.id)
        await interaction.response.send_modal(modal)

class GeneralTicketButtons(discord.ui.View):
    def __init__(self, ticket_type: str = None, user_id: int = None, channel_id: int = None):
        super().__init__(timeout=None)
        self.ticket_type = ticket_type
        self.user_id = user_id
        self.channel_id = channel_id
    
    @discord.ui.button(label="Вирішено", style=discord.ButtonStyle.green, custom_id="resolve_general_ticket")
    async def resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Дозволяємо всім користувачам закривати загальні тікети
        if not all([self.ticket_type, self.user_id]):
            ticket_data = await db.tickets.find_one({"channel_id": interaction.channel.id})
            if ticket_data:
                self.ticket_type = ticket_data.get("ticket_type")
                self.user_id = ticket_data.get("user_id")
        
        user = interaction.guild.get_member(self.user_id)
        config = TICKET_TYPES.get(self.ticket_type, {"name": "Невідомий тип"})
        
        await db.tickets.update_one(
            {"channel_id": interaction.channel.id},
            {"$set": {"status": "resolved", "resolved_by": interaction.user.id, "resolved_at": datetime.now()}}
        )
        
        embed = discord.Embed(
            title="Тікет вирішено",
            description=f"**Користувач:** {user.mention if user else 'Користувач покинув сервер'}\n" +
                       f"**Тип тікета:** {config['name']}\n" +
                       f"**Вирішив:** {interaction.user.mention}",
            color=0x57f287,
            timestamp=datetime.now()
        )
        embed.add_field(
            name="Статус",
            value="Тікет успішно вирішено та готовий до закриття",
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed, view=TicketCloseView())
        
        # DM користувачу
        if user:
            dm_embed = discord.Embed(
                title="<:palka:1412777364387135589> Тікет вирішено",
                description=f"Ваш тікет типу **{config['name']}** було вирішено.\n\n" +
                           f"**Сервер:** {interaction.guild.name}\n" +
                           f"**Вирішив:** {interaction.user.mention}\n\n" +
                           f"Дякуємо за звернення!",
                color=0x57f287,
                timestamp=datetime.now()
            )
            await send_dm_notification(user, dm_embed)

class TicketMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        self.bot.add_view(TicketMainView())
        self.bot.add_view(RoleApplicationButtons())
        self.bot.add_view(GeneralTicketButtons())
        self.bot.add_view(TicketCloseView())
    
    # Група команд для тікетів
    ticket_group = app_commands.Group(name="ticket", description="Команди для керування системою тікетів")
    
    @ticket_group.command(name="panel", description="Створити панель тікетів")
    @app_commands.describe(
        channel="Канал де створити панель (за замовчуванням поточний)",
        log_channel="Канал для логування дій",
        category="Категорія для тікетів",
        setup_moderators="Налаштувати модераторські ролі після створення панелі"
    )
    async def create_panel(self, interaction: discord.Interaction, 
                          channel: discord.TextChannel = None,
                          log_channel: discord.TextChannel = None,
                          category: discord.CategoryChannel = None,
                          setup_moderators: bool = False):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Тільки адміністратори можуть використовувати цю команду!", ephemeral=True)
            return
        
        target_channel = channel or interaction.channel
        
        # Оновлюємо конфігурацію
        changes_made = []
        updates = {}
        
        if log_channel:
            updates["log_channel_id"] = log_channel.id
            changes_made.append(f"Канал логів: {log_channel.mention}")
        
        if category:
            updates["category_id"] = category.id
            changes_made.append(f"Категорія тікетів: {category.name}")
        
        if updates:
            await update_guild_config(interaction.guild.id, updates)
        
        # Головний embed системи тікетів
        main_embed = discord.Embed(
            title="<:palka:1412777364387135589> Система тікетів підтримки",
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        
        # Доступні типи тікетів
        types_text = (
            "**<:odym:1412519796456689714> Заявка на роль** | Подати заявку на отримання ролі\n"
            "**<:dva:1412519805185163274> Пропозиція для сервера** | Поділитися ідеями для покращення сервера\n"
            "**<:try:1412519816245547038> Звіт про баг** | Повідомити про технічні проблеми\n"
            "**<:chetyri:1412519826274127973> Загальна підтримка** | Питання або допомога від модерації\n"
            "**<:pyat:1412519858960339064> Скарга** | Подати скаргу на користувача або ситуацію"
        )
        
        main_embed.add_field(
            name="<:palka:1412777364387135589> • Доступні типи тікетів :",
            value=types_text,
            inline=False
        )
        
        # Правила використання
        rules_text = (
            "**—** Один активний тікет кожного типу на користувача\n"
            "**—** Відповідайте чесно та детально\n"
            "**—** Будьте ввічливими з модерацією\n"
            "**—** Не створюйте тікети без потреби"
        )
        
        main_embed.add_field(
            name="<:palka:1412777364387135589> • Правила використання :",
            value=rules_text,
            inline=False
        )
        
        view = TicketMainView()
        await target_channel.send(embed=main_embed, view=view)
        
        success_embed = discord.Embed(
            title="Панель тікетів створено",
            description=f"Панель успішно розміщено в {target_channel.mention}",
            color=0x57f287
        )
        
        if changes_made:
            success_embed.add_field(
                name="Налаштування оновлено",
                value="\n".join(changes_made),
                inline=False
            )
        
        if setup_moderators:
            guild_config = await get_guild_config(interaction.guild.id)
            view = RolesPaginationView(interaction.guild, guild_config, "moderator_roles")
            embed = view.create_embed()
            success_embed.add_field(
                name="Налаштування модераторів",
                value="Оберіть модераторські ролі в меню нижче",
                inline=False
            )
            await interaction.response.send_message(embed=success_embed, ephemeral=True)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=success_embed, ephemeral=True)
    
    @ticket_group.command(name="moderators", description="Налаштування модераторських ролей")
    @app_commands.describe(action="Дія з ролями")
    @app_commands.choices(action=[
        app_commands.Choice(name="Додати ролі", value="add"),
        app_commands.Choice(name="Видалити ролі", value="remove"),
        app_commands.Choice(name="Показати список", value="list"),
        app_commands.Choice(name="Очистити всі", value="clear")
    ])
    async def moderators(self, interaction: discord.Interaction, action: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Тільки адміністратори можуть використовувати цю команду!", ephemeral=True)
            return
        
        guild_config = await get_guild_config(interaction.guild.id)
        
        if action == "list":
            if not guild_config.get("moderator_role_ids"):
                embed = discord.Embed(
                    title="Модераторські ролі",
                    description="Не налаштовано модераторських ролей.\nТільки адміністратори можуть керувати тікетами.",
                    color=0xfee75c
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(title="Модераторські ролі", color=0x2b2d31)
            
            roles_list = []
            valid_roles = []
            for i, role_id in enumerate(guild_config["moderator_role_ids"], 1):
                role = interaction.guild.get_role(role_id)
                if role:
                    roles_list.append(f"{i}. {role.mention}")
                    valid_roles.append(role_id)
                else:
                    roles_list.append(f"{i}. Роль видалена (ID: {role_id})")
            
            # Оновлюємо конфіг якщо знайдені видалені ролі
            if len(valid_roles) != len(guild_config["moderator_role_ids"]):
                await update_guild_config(interaction.guild.id, {"moderator_role_ids": valid_roles})
            
            embed.add_field(
                name=f"Ролей: {len(valid_roles)}",
                value="\n".join(roles_list) if roles_list else "Немає ролей",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif action == "add":
            view = RolesPaginationView(interaction.guild, guild_config, "moderator_roles")
            embed = view.create_embed()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        elif action == "remove":
            if not guild_config.get("moderator_role_ids"):
                embed = discord.Embed(
                    title="Видалення ролей",
                    description="Немає ролей для видалення",
                    color=0xed4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            view = RemoveRolesView(interaction.guild, guild_config, "moderator_roles")
            embed = view.create_embed()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        elif action == "clear":
            if not guild_config.get("moderator_role_ids"):
                embed = discord.Embed(
                    title="Очищення ролей",
                    description="Немає ролей для очищення",
                    color=0xfee75c
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            await update_guild_config(interaction.guild.id, {"moderator_role_ids": []})
            
            embed = discord.Embed(
                title="Модераторські ролі очищено",
                description="Всі модераторські ролі видалено.\nТепер тільки адміністратори можуть керувати тікетами.",
                color=0x57f287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @ticket_group.command(name="roles", description="Керування ролями для заявок")
    @app_commands.describe(action="Дія з ролями")
    @app_commands.choices(action=[
        app_commands.Choice(name="Додати ролі", value="add"),
        app_commands.Choice(name="Видалити ролі", value="remove"),
        app_commands.Choice(name="Показати список", value="list"),
        app_commands.Choice(name="Очистити всі", value="clear")
    ])
    async def roles(self, interaction: discord.Interaction, action: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Тільки адміністратори можуть використовувати цю команду!", ephemeral=True)
            return
        
        guild_config = await get_guild_config(interaction.guild.id)
        
        if action == "list":
            if not guild_config.get("available_roles"):
                embed = discord.Embed(
                    title="Ролі для тікетів",
                    description="Немає налаштованих ролей для заявок",
                    color=0xed4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(title="Доступні ролі для заявок", color=0x2b2d31)
            
            roles_list = []
            valid_roles = []
            for i, role_id in enumerate(guild_config["available_roles"], 1):
                role = interaction.guild.get_role(role_id)
                if role:
                    roles_list.append(f"{i}. {role.mention}")
                    valid_roles.append(role_id)
                else:
                    roles_list.append(f"{i}. Роль видалена (ID: {role_id})")
            
            # Оновлюємо конфіг якщо знайдені видалені ролі
            if len(valid_roles) != len(guild_config["available_roles"]):
                await update_guild_config(interaction.guild.id, {"available_roles": valid_roles})
            
            embed.add_field(
                name=f"Ролей: {len(valid_roles)}",
                value="\n".join(roles_list) if roles_list else "Немає ролей",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif action == "add":
            view = RolesPaginationView(interaction.guild, guild_config, "ticket_roles")
            embed = view.create_embed()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        elif action == "remove":
            if not guild_config.get("available_roles"):
                embed = discord.Embed(
                    title="Видалення ролей",
                    description="Немає ролей для видалення",
                    color=0xed4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            view = RemoveRolesView(interaction.guild, guild_config, "ticket_roles")
            embed = view.create_embed()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        elif action == "clear":
            if not guild_config.get("available_roles"):
                embed = discord.Embed(
                    title="Очищення ролей",
                    description="Немає ролей для очищення",
                    color=0xfee75c
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            await update_guild_config(interaction.guild.id, {"available_roles": []})
            
            embed = discord.Embed(
                title="Ролі для тікетів очищено",
                description="Всі ролі для заявок видалено.\nКористувачі не зможуть подавати заявки на ролі до налаштування нових.",
                color=0x57f287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @ticket_group.command(name="info", description="Інформація та статистика")
    @app_commands.describe(type="Тип інформації")
    @app_commands.choices(type=[
        app_commands.Choice(name="Поточні налаштування", value="settings"),
        app_commands.Choice(name="Статистика тікетів", value="stats")
    ])
    async def info(self, interaction: discord.Interaction, type: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Тільки адміністратори можуть використовувати цю команду!", ephemeral=True)
            return
        
        if type == "settings":
            guild_config = await get_guild_config(interaction.guild.id)
            embed = discord.Embed(title="Поточні налаштування", color=0x2b2d31)
            
            # Ролі модераторів
            if guild_config.get("moderator_role_ids"):
                mod_roles = []
                for role_id in guild_config["moderator_role_ids"]:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        mod_roles.append(role.mention)
                embed.add_field(
                    name="Ролі модераторів", 
                    value="\n".join(mod_roles) if mod_roles else "Не налаштовано", 
                    inline=True
                )
            else:
                embed.add_field(name="Ролі модераторів", value="Не налаштовано", inline=True)
            
            log_channel = interaction.guild.get_channel(guild_config["log_channel_id"]) if guild_config.get("log_channel_id") else None
            category = interaction.guild.get_channel(guild_config["category_id"]) if guild_config.get("category_id") else None
            
            embed.add_field(name="Канал логів", value=log_channel.mention if log_channel else "Не налаштовано", inline=True)
            embed.add_field(name="Категорія", value=category.name if category else "Не налаштовано", inline=True)
            embed.add_field(name="Кількість ролей", value=f"{len(guild_config.get('available_roles', []))} ролей", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif type == "stats":
            # Загальна статистика
            total_tickets = await db.tickets.count_documents({"guild_id": interaction.guild.id})
            open_tickets = await db.tickets.count_documents({"guild_id": interaction.guild.id, "status": "open"})
            
            # Статистика за типами
            type_stats = {}
            for ticket_type in TICKET_TYPES.keys():
                count = await db.tickets.count_documents({
                    "guild_id": interaction.guild.id, 
                    "ticket_type": ticket_type
                })
                type_stats[ticket_type] = count
            
            # Статистика за тиждень
            week_stats = await get_week_stats(interaction.guild.id)
            week_total = sum(count for _, count in week_stats)
            
            embed = discord.Embed(
                title="Статистика тікетів",
                color=0x2b2d31,
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="Загальна статистика",
                value=f"**Всього тікетів:** {total_tickets}\n**Відкритих зараз:** {open_tickets}\n**За останні 7 днів:** {week_total}",
                inline=False
            )
            
            # Статистика по типах
            if any(type_stats.values()):
                type_text = []
                for ticket_type, count in type_stats.items():
                    if count > 0:
                        config = TICKET_TYPES[ticket_type]
                        type_text.append(f"{config['emoji']} {config['name']}: {count}")
                
                if type_text:
                    embed.add_field(
                        name="За типами",
                        value="\n".join(type_text),
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
    print("Ticket System завантажено")