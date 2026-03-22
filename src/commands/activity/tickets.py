"""
Система тікетів — одна команда /ticket відкриває повну адмін-панель.

Фічі:
- Авто-нумерація тікетів (counter per guild)
- Claim: модератор «бере» тікет
- Close → Modal із причиною → embed у лог-канал + DM відкривачу
- Лог-канал налаштовується через /ticket UI
- Вибір каналу для публікації панелі
"""
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

from modules.logger import Logger
from modules.db import get_database
from utils.ui_contract import add_section, compact_kv, gameplay_result_embed, set_surface_footer, surface_embed

log = Logger("Tickets")
db = get_database()
collection = db.ticket_config

# ── Кастомні емодзі ──────────────────────────────────────────────────────────
E_TICKET      = "<:ticket:1476195902002696374>"
E_CLOSED      = "<:closed:1476207781840158741>"
E_OPENED      = "<:openedckeckmark:1476208751567441941>"
E_CLOCK       = "<:clock:1476209087804084328>"
E_CLAIMED     = "<:claimed:1476209482236301322>"
E_REASON      = "<:reasonqiestion:1476209697919860777>"
E_DELETE      = "<:deleteticket:1476196622177271922>"
E_SUPPORTROLE = "<:supportrole:1476198036567756841>"

EMBED_COLOR = 0x1a1a2e

# ── DB helpers ────────────────────────────────────────────────────────────────

async def get_config(guild_id: int) -> dict:
    return await collection.find_one({"_id": guild_id}) or {}

async def update_config(guild_id: int, data: dict):
    await collection.update_one({"_id": guild_id}, {"$set": data}, upsert=True)

async def next_ticket_id(guild_id: int) -> int:
    result = await collection.find_one_and_update(
        {"_id": guild_id},
        {"$inc": {"ticket_counter": 1}},
        upsert=True,
        return_document=True,
    )
    return result.get("ticket_counter", 1)

# ── Modals ────────────────────────────────────────────────────────────────────

class CloseReasonModal(discord.ui.Modal, title="Закрити тікет"):
    reason = discord.ui.TextInput(
        label="Причина закриття",
        placeholder="Залиш порожнім якщо причини немає...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=512,
    )

    def __init__(self, ticket_data: dict):
        super().__init__()
        self._ticket_data = ticket_data

    async def on_submit(self, interaction: discord.Interaction):
        reason_text = self.reason.value.strip() or "Причину не вказано"
        await _do_close_ticket(interaction, self._ticket_data, reason_text)

class RoleInputModal(discord.ui.Modal, title="Додати роль за ID"):
    role_id = discord.ui.TextInput(label="ID ролі", placeholder="Наприклад: 123456789012345678")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            r_id = int(self.role_id.value.strip())
        except ValueError:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Невірний формат ID.", ephemeral=True)
            return

        role = interaction.guild.get_role(r_id)
        if not role:
            try:
                role = await interaction.guild.fetch_role(r_id)
            except (discord.NotFound, discord.HTTPException):
                role = None

        if not role:
            await interaction.response.send_message(f"<:cutiex:1480246146076119132> Роль `{r_id}` не знайдена.", ephemeral=True)
            return

        config = await get_config(interaction.guild.id)
        current = config.get("support_role_ids", [])
        if r_id not in current:
            current.append(r_id)
            await update_config(interaction.guild.id, {"support_role_ids": current})
            await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Роль {role.mention} додана.", ephemeral=True)
        else:
            await interaction.response.send_message(f"<:warn:1477376152191373504> Роль {role.mention} вже в списку.", ephemeral=True)

class PanelContentModal(discord.ui.Modal, title="Налаштування панелі"):
    panel_title = discord.ui.TextInput(label="Заголовок", default="Служба підтримки")
    panel_desc = discord.ui.TextInput(
        label="Опис",
        style=discord.TextStyle.paragraph,
        default="Натисніть кнопку нижче, щоб зв'язатися з адміністрацією.",
    )

    def __init__(self, current_title: str, current_desc: str):
        super().__init__()
        self.panel_title.default = current_title
        self.panel_desc.default = current_desc

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("<:cutiecheckmark:1479120440734650389> Текст панелі оновлено!", ephemeral=True)

class ButtonConfigModal(discord.ui.Modal, title="Додати кнопку"):
    btn_label = discord.ui.TextInput(label="Текст кнопки", placeholder="Створити тікет")
    btn_emoji = discord.ui.TextInput(label="Emoji (необов'язково)", required=False, placeholder="🎫")

    def __init__(self, view_instance):
        super().__init__()
        self.view_instance = view_instance

    async def on_submit(self, interaction: discord.Interaction):
        if len(self.view_instance.custom_buttons) >= 10:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Максимум 10 кнопок!", ephemeral=True)
            return
        label = self.btn_label.value.strip() or "Тікет"
        emoji_str = self.btn_emoji.value.strip()
        self.view_instance.custom_buttons.append({
            "label": label,
            "emoji": emoji_str if emoji_str else None,
            "style": discord.ButtonStyle.blurple,
        })
        await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Кнопку «{label}» додано!", ephemeral=True)

# ── Ticket close logic ────────────────────────────────────────────────────────

def _build_close_embed(
    guild: discord.Guild,
    ticket_id: int,
    opened_by,
    closed_by: discord.Member,
    opened_at,
    claimed_by,
    reason: str,
) -> discord.Embed:
    embed = discord.Embed(title="Ticket Closed", color=EMBED_COLOR, timestamp=datetime.now(timezone.utc))
    embed.set_author(name=guild.name)

    opened_at_str = (
        opened_at.strftime("%d %B %Y  %I:%M %p")
        if opened_at else "Невідомо"
    )

    embed.description = (
        f"{E_TICKET}  **Ticket ID**\n{ticket_id}\n\n"
        f"{E_OPENED}  **Opened By**\n{opened_by.mention if opened_by else 'Невідомо'}\n\n"
        f"{E_CLOSED}  **Closed By**\n{closed_by.mention}\n\n"
        f"{E_CLOCK}  **Open Time**\n{opened_at_str}\n\n"
        f"{E_CLAIMED}  **Claimed By**\n{claimed_by.mention if claimed_by else 'Not claimed'}\n\n"
        f"{E_REASON}  **Reason**\n{reason}"
    )
    return embed

def _build_close_embed(
    guild: discord.Guild,
    ticket_id: int,
    opened_by,
    closed_by: discord.Member,
    opened_at,
    claimed_by,
    reason: str,
) -> discord.Embed:
    opened_at_str = opened_at.strftime("%d %B %Y  %I:%M %p") if opened_at else "Невідомо"
    embed = surface_embed("admin", "Ticket closed", tone="warning")
    embed.timestamp = datetime.now(timezone.utc)
    embed.set_author(name=guild.name)
    add_section(
        embed,
        "Підсумок",
        [
            compact_kv("Ticket ID", str(ticket_id)),
            compact_kv("Opened by", opened_by.mention if opened_by else "Невідомо"),
            compact_kv("Closed by", closed_by.mention),
            compact_kv("Open time", opened_at_str),
            compact_kv("Claimed by", claimed_by.mention if claimed_by else "Not claimed"),
            compact_kv("Reason", reason),
        ],
    )
    set_surface_footer(embed, "admin", "Лог і DM використовують той самий підсумковий шаблон.")
    return embed


async def _do_close_ticket(interaction: discord.Interaction, ticket_data: dict, reason: str):
    guild   = interaction.guild
    channel = interaction.channel

    opened_by  = guild.get_member(ticket_data.get("opened_by"))
    closed_by  = interaction.user
    claimed_id = ticket_data.get("claimed_by")
    claimed_by = guild.get_member(claimed_id) if claimed_id else None
    opened_at  = ticket_data.get("opened_at")
    ticket_id  = ticket_data.get("ticket_id", "?")

    embed = _build_close_embed(guild, ticket_id, opened_by, closed_by, opened_at, claimed_by, reason)

    config = await get_config(guild.id)
    log_ch_id = config.get("log_channel_id")
    if log_ch_id:
        log_ch = guild.get_channel(log_ch_id)
        if log_ch:
            try:
                await log_ch.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    if opened_by:
        try:
            await opened_by.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    await interaction.response.send_message("Тікет буде закрито через 5 секунд...", ephemeral=True)
    await asyncio.sleep(5)
    try:
        await channel.delete()
    except discord.HTTPException:
        pass

    await db.active_tickets.delete_one({"channel_id": channel.id})

# ── Persistent Views ──────────────────────────────────────────────────────────

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _get_ticket_data(self, channel_id: int) -> dict:
        return await db.active_tickets.find_one({"channel_id": channel_id}) or {}

    @discord.ui.button(
        label="Взяти тікет",
        emoji=discord.PartialEmoji.from_str(E_CLAIMED),
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_claim_v2",
    )
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await get_config(interaction.guild.id)
        support_ids = set(config.get("support_role_ids", []))
        member_ids  = {r.id for r in interaction.user.roles}

        if not interaction.user.guild_permissions.administrator and not support_ids.intersection(member_ids):
            await interaction.response.send_message("<:cutiex:1480246146076119132> Тільки персонал підтримки може взяти тікет.", ephemeral=True)
            return

        td = await self._get_ticket_data(interaction.channel.id)
        if td.get("claimed_by"):
            claimer = interaction.guild.get_member(td["claimed_by"])
            await interaction.response.send_message(
                f"<:warn:1477376152191373504> Тікет вже взятий {claimer.mention if claimer else 'кимось'}.", ephemeral=True
            )
            return

        await db.active_tickets.update_one(
            {"channel_id": interaction.channel.id},
            {"$set": {"claimed_by": interaction.user.id}},
        )
        embed = discord.Embed(
            description=f"{E_CLAIMED} {interaction.user.mention} взяв цей тікет.",
            color=EMBED_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(
        label="Закрити тікет",
        emoji=discord.PartialEmoji.from_str(E_DELETE),
        style=discord.ButtonStyle.red,
        custom_id="ticket_close_v2",
    )
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        td = await self._get_ticket_data(interaction.channel.id)
        await interaction.response.send_modal(CloseReasonModal(td))

class TicketView(discord.ui.View):
    """Persistent view для публічної панелі (біла кнопка)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Створити тікет",
        emoji=discord.PartialEmoji.from_str(E_TICKET),
        style=discord.ButtonStyle.secondary,   
        custom_id="ticket_create_v2",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket_routine(interaction)

class DynamicTicketView(discord.ui.View):
    def __init__(self, buttons_config: list):
        super().__init__(timeout=None)
        self._add_buttons(buttons_config)

    def _add_buttons(self, buttons_config: list):
        if not buttons_config:
            btn = discord.ui.Button(
                label="Створити тікет",
                emoji=discord.PartialEmoji.from_str(E_TICKET),
                style=discord.ButtonStyle.secondary,
                custom_id="ticket_create_v2",
            )
            btn.callback = self._ticket_callback
            self.add_item(btn)
            return

        for i, bd in enumerate(buttons_config):
            emoji = None
            if bd.get("emoji"):
                try:
                    emoji = discord.PartialEmoji.from_str(bd["emoji"])
                except Exception:
                    emoji = None
            btn = discord.ui.Button(
                label=bd["label"], emoji=emoji,
                style=bd.get("style", discord.ButtonStyle.blurple),
                custom_id=f"ticket_create_{i}_v2",
            )
            btn.callback = self._ticket_callback
            self.add_item(btn)

    async def _ticket_callback(self, interaction: discord.Interaction):
        await create_ticket_routine(interaction)

# ── Create ticket ─────────────────────────────────────────────────────────────

async def create_ticket_routine(interaction: discord.Interaction):
    guild  = interaction.guild
    user   = interaction.user
    config = await get_config(guild.id)

    category_id = config.get("category_id")
    category    = guild.get_channel(category_id) if category_id else None
    if not category:
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            category = await guild.create_category("Tickets")

    channel_name = f"ticket-{user.name}".lower().replace(" ", "-")
    existing = discord.utils.get(guild.text_channels, name=channel_name, category_id=category.id)
    if existing:
        await interaction.response.send_message(f"<:cutiex:1480246146076119132> Відкритий тікет: {existing.mention}", ephemeral=True)
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
    }
    for rid in config.get("support_role_ids", []):
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    try:
        channel = await guild.create_text_channel(
            name=channel_name, category=category, overwrites=overwrites, topic=f"User ID: {user.id}"
        )
    except discord.HTTPException as e:
        await interaction.response.send_message(f"<:cutiex:1480246146076119132> Помилка: {e}", ephemeral=True)
        log.error(f"Failed to create ticket for {user}: {e}")
        return

    ticket_id = await next_ticket_id(guild.id)
    opened_at = datetime.now(timezone.utc)

    await db.active_tickets.insert_one({
        "channel_id": channel.id,
        "guild_id":   guild.id,
        "ticket_id":  ticket_id,
        "opened_by":  user.id,
        "opened_at":  opened_at,
        "claimed_by": None,
    })

    await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Тікет #{ticket_id}: {channel.mention}", ephemeral=True)

    embed = discord.Embed(
        description=(
            f"Привіт {user.mention}!\n"
            f"Опишіть проблему — адміністрація зв'яжеться найближчим часом.\n\n"
            f"{E_TICKET}  **Ticket #{ticket_id}**"
        ),
        color=EMBED_COLOR,
    )
    embed.set_author(name=guild.name)
    await channel.send(embed=embed, view=TicketControlView())

# ── Admin Panel ───────────────────────────────────────────────────────────────

class TicketAdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.embed_title   = "Служба підтримки"
        self.embed_desc    = "Натисніть кнопку нижче, щоб зв'язатися з адміністрацією."
        self.custom_buttons: list = []
        self.target_channel_id: int | None = None

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.category],
        placeholder="Категорія для тікетів",
        min_values=0, max_values=1, row=0,
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        cat = select.values[0] if select.values else None
        await update_config(interaction.guild.id, {"category_id": cat.id if cat else None})
        await interaction.response.send_message(
            f"<:cutiecheckmark:1479120440734650389> Категорія: {cat.mention if cat else 'Стандартна (Tickets)'}", ephemeral=True
        )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Лог-канал (закриті тікети)",
        min_values=0, max_values=1, row=1,
    )
    async def select_log_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        ch = select.values[0] if select.values else None
        await update_config(interaction.guild.id, {"log_channel_id": ch.id if ch else None})
        await interaction.response.send_message(
            f"<:cutiecheckmark:1479120440734650389> Лог-канал: {ch.mention if ch else 'відключено'}", ephemeral=True
        )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Канал для публікації панелі",
        min_values=0, max_values=1, row=2,
    )
    async def select_panel_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        ch = select.values[0] if select.values else None
        self.target_channel_id = ch.id if ch else None
        await interaction.response.send_message(
            f"<:cutiecheckmark:1479120440734650389> Панель буде надіслана в: {ch.mention if ch else 'поточний канал'}", ephemeral=True
        )

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Ролі підтримки",
        min_values=0, max_values=20, row=3,
    )
    async def select_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role_ids = [r.id for r in select.values]
        await update_config(interaction.guild.id, {"support_role_ids": role_ids})
        mentions = ", ".join(r.mention for r in select.values) or "очищено"
        await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Ролі підтримки: {mentions}", ephemeral=True)

    @discord.ui.button(label="Роль за ID", style=discord.ButtonStyle.secondary, row=4)
    async def add_role_id(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RoleInputModal())

    @discord.ui.button(label="Текст панелі", style=discord.ButtonStyle.secondary, row=4)
    async def edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PanelContentModal(self.embed_title, self.embed_desc)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.embed_title = modal.panel_title.value
        self.embed_desc  = modal.panel_desc.value
        await interaction.edit_original_response(embed=self._build_preview())

    @discord.ui.button(label="Додати кнопку", style=discord.ButtonStyle.secondary, row=4)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.custom_buttons) >= 10:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Максимум 10 кнопок!", ephemeral=True)
            return
        await interaction.response.send_modal(ButtonConfigModal(self))

    @discord.ui.button(label="📋 Надіслати панель", style=discord.ButtonStyle.success, row=4)
    async def send_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        if self.target_channel_id:
            target_ch = interaction.guild.get_channel(self.target_channel_id)
        else:
            target_ch = interaction.channel

        if not target_ch:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Канал не знайдено.", ephemeral=True)
            return

        try:
            final_view = DynamicTicketView(self.custom_buttons) if self.custom_buttons else TicketView()
            await target_ch.send(embed=self._build_preview(), view=final_view)
            await interaction.response.edit_message(
                content=f"<:cutiecheckmark:1479120440734650389> Панель надіслана в {target_ch.mention}!", embed=None, view=None
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(f"<:cutiex:1480246146076119132> Помилка: {e}", ephemeral=True)

    def _build_preview(self) -> discord.Embed:
        return discord.Embed(title=self.embed_title, description=self.embed_desc, color=EMBED_COLOR)

# ── Cog ───────────────────────────────────────────────────────────────────────

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketControlView())
        await collection.create_index("_id")
        await db.active_tickets.create_index("channel_id", unique=True, background=True)
        await db.active_tickets.create_index("guild_id", background=True)
        log.info("Ticket persistent views registered")

    @app_commands.command(name="ticket", description="Управління системою тікетів")
    @app_commands.default_permissions(administrator=True)
    async def ticket_admin(self, interaction: discord.Interaction):
        config   = await get_config(interaction.guild.id)
        cat_id   = config.get("category_id")
        log_id   = config.get("log_channel_id")
        role_ids = config.get("support_role_ids", [])

        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_author(name="Система тікетів")
        embed.description = (
            f"{E_TICKET}  **Категорія:** {'<#' + str(cat_id) + '>' if cat_id else 'Стандартна'}\n"
            f"**Лог-канал:** {'<#' + str(log_id) + '>' if log_id else 'Не налаштовано'}\n"
            f"{E_SUPPORTROLE}  **Ролі підтримки:** "
            + (", ".join(f"<@&{rid}>" for rid in role_ids) or "Не налаштовано") + "\n\n"
            "Використовуй селектори нижче для налаштування системи."
        )
        await interaction.response.send_message(embed=embed, view=TicketAdminView(), ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
