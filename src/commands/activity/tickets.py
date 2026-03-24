"""
Система тікетів:
- одна команда /ticket для адмін-налаштувань
- claim для staff workflow
- close через modal із причиною
- transcript .txt у лог-канал під час закриття
- DM opener-у з підсумком закриття
"""

import asyncio
import io
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from modules.db import get_database
from modules.logger import Logger
from utils.ui_contract import add_section, compact_kv, set_surface_footer, surface_embed

log = Logger("Tickets")
db = get_database()
collection = db.ticket_config

E_TICKET = "<:ticket:1485608010192519300>"
E_CLOSED = "<:close:1485598320935174317>"
E_OPENED = "<:check:1485597845883981905>"
E_CLOCK = "<:clock:1485618008784113796>"
E_CLAIMED = "<:hammer:1485606127696609412>"
E_REASON = "<:help:1485604736588583053>"
E_DELETE = "<:trash:1485598963590758420>"
E_SUPPORTROLE = "<:ticket:1485608010192519300>"
E_CLIPBOARD = "<:clipboard:1485728386453340331>"

EMBED_COLOR = 0x1A1A2E
TRANSCRIPT_MAX_BYTES = 7_500_000


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


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "Невідомо"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def _safe_text(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("\r", "").strip()


def _member_label(member: discord.abc.User | None, fallback: str) -> str:
    return member.mention if member else fallback


def _truncate_transcript(raw: str) -> bytes:
    data = raw.encode("utf-8")
    if len(data) <= TRANSCRIPT_MAX_BYTES:
        return data

    notice = (
        "[Transcript обрізано, бо файл перевищив ліміт Discord.]\n"
        "[Збережено початок переписки.]\n\n"
    ).encode("utf-8")
    allowed = max(0, TRANSCRIPT_MAX_BYTES - len(notice))
    return notice + data[:allowed]


async def _build_transcript_text(channel: discord.TextChannel) -> str:
    lines = [
        f"Ticket transcript: #{channel.name}",
        f"Guild ID: {channel.guild.id}",
        f"Channel ID: {channel.id}",
        f"Generated at: {_fmt_dt(datetime.now(timezone.utc))}",
        "-" * 72,
    ]

    async for message in channel.history(limit=None, oldest_first=True):
        created = _fmt_dt(message.created_at)
        author = f"{message.author} ({message.author.id})"
        lines.append(f"[{created}] {author}")

        content = _safe_text(message.content)
        if content:
            lines.append(content)
        else:
            lines.append("[без тексту]")

        if message.attachments:
            lines.append("Attachments:")
            for attachment in message.attachments:
                lines.append(f"- {attachment.filename}: {attachment.url}")

        if message.embeds:
            lines.append(f"[Embeds: {len(message.embeds)}]")

        if message.stickers:
            lines.append(f"[Stickers: {len(message.stickers)}]")

        lines.append("")

    return "\n".join(lines)


def _build_transcript_file(ticket_id: int | str, transcript_text: str) -> discord.File:
    payload = _truncate_transcript(transcript_text)
    filename = f"ticket-{ticket_id}-transcript.txt"
    return discord.File(io.BytesIO(payload), filename=filename)


def _build_close_embed(
    guild: discord.Guild,
    ticket_id: int | str,
    opened_by: discord.Member | None,
    closed_by: discord.Member,
    opened_at: datetime | None,
    closed_at: datetime,
    claimed_by: discord.Member | None,
    reason: str,
) -> discord.Embed:
    embed = surface_embed("admin", "Тікет закрито", tone="warning")
    embed.timestamp = closed_at
    embed.set_author(name=guild.name)
    add_section(
        embed,
        "Підсумок",
        [
            compact_kv("Ticket ID", str(ticket_id)),
            compact_kv("Відкрив", _member_label(opened_by, "Невідомо")),
            compact_kv("Взяв", _member_label(claimed_by, "Не взято")),
            compact_kv("Закрив", closed_by.mention),
            compact_kv("Відкрито", _fmt_dt(opened_at)),
            compact_kv("Закрито", _fmt_dt(closed_at)),
            compact_kv("Причина", reason),
        ],
    )
    set_surface_footer(embed, "admin", "Transcript надсилається в лог-канал, opener отримує DM-підсумок.")
    return embed


async def _do_close_ticket(interaction: discord.Interaction, ticket_data: dict, reason: str):
    guild = interaction.guild
    channel = interaction.channel
    closed_at = datetime.now(timezone.utc)

    opened_by = guild.get_member(ticket_data.get("opened_by"))
    closed_by = interaction.user
    claimed_id = ticket_data.get("claimed_by")
    claimed_by = guild.get_member(claimed_id) if claimed_id else None
    opened_at = ticket_data.get("opened_at")
    ticket_id = ticket_data.get("ticket_id", "?")

    embed = _build_close_embed(
        guild=guild,
        ticket_id=ticket_id,
        opened_by=opened_by,
        closed_by=closed_by,
        opened_at=opened_at,
        closed_at=closed_at,
        claimed_by=claimed_by,
        reason=reason,
    )

    transcript_text = await _build_transcript_text(channel)

    config = await get_config(guild.id)
    log_ch_id = config.get("log_channel_id")
    transcript_logged = False
    if log_ch_id:
        log_ch = guild.get_channel(log_ch_id)
        if log_ch:
            try:
                transcript_file = _build_transcript_file(ticket_id, transcript_text)
                await log_ch.send(embed=embed, file=transcript_file)
                transcript_logged = True
            except (discord.Forbidden, discord.HTTPException):
                log.warning(f"Failed to send ticket transcript to log channel {log_ch_id} in guild {guild.id}")

    if opened_by:
        try:
            await opened_by.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    notice = "Тікет буде закрито через 5 секунд."
    if transcript_logged:
        notice += " Transcript надіслано в лог-канал."
    await interaction.response.send_message(notice, ephemeral=True)

    await asyncio.sleep(5)
    deleted = False
    try:
        await channel.delete()
        deleted = True
    except discord.HTTPException:
        log.error(f"Failed to delete ticket channel {channel.id} in guild {guild.id}")

    if deleted:
        await db.active_tickets.delete_one({"channel_id": channel.id})


class CloseReasonModal(discord.ui.Modal, title="Закрити тікет"):
    reason = discord.ui.TextInput(
        label="Причина закриття",
        placeholder="Залиш порожнім, якщо причина не потрібна...",
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
            await interaction.response.send_message(f"{E_CLOSED} Невірний формат ID.", ephemeral=True)
            return

        role = interaction.guild.get_role(r_id)
        if not role:
            try:
                role = await interaction.guild.fetch_role(r_id)
            except (discord.NotFound, discord.HTTPException):
                role = None

        if not role:
            await interaction.response.send_message(f"{E_CLOSED} Роль `{r_id}` не знайдено.", ephemeral=True)
            return

        config = await get_config(interaction.guild.id)
        current = config.get("support_role_ids", [])
        if r_id not in current:
            current.append(r_id)
            await update_config(interaction.guild.id, {"support_role_ids": current})
            await interaction.response.send_message(f"{E_OPENED} Роль {role.mention} додана.", ephemeral=True)
            return

        await interaction.response.send_message(f"{E_REASON} Роль {role.mention} вже у списку.", ephemeral=True)


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
        await interaction.response.send_message(f"{E_OPENED} Текст панелі оновлено.", ephemeral=True)


class ButtonConfigModal(discord.ui.Modal, title="Додати кнопку"):
    btn_label = discord.ui.TextInput(label="Текст кнопки", placeholder="Створити тікет")
    btn_emoji = discord.ui.TextInput(label="Emoji (необов'язково)", required=False, placeholder=E_TICKET)

    def __init__(self, view_instance):
        super().__init__()
        self.view_instance = view_instance

    async def on_submit(self, interaction: discord.Interaction):
        if len(self.view_instance.custom_buttons) >= 10:
            await interaction.response.send_message(f"{E_CLOSED} Максимум 10 кнопок.", ephemeral=True)
            return

        label = self.btn_label.value.strip() or "Тікет"
        emoji_str = self.btn_emoji.value.strip() or None
        self.view_instance.custom_buttons.append(
            {
                "label": label,
                "emoji": emoji_str,
                "style": discord.ButtonStyle.blurple,
            }
        )
        await interaction.response.send_message(f"{E_OPENED} Кнопку «{label}» додано.", ephemeral=True)


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
        member_ids = {role.id for role in interaction.user.roles}

        if not interaction.user.guild_permissions.administrator and not support_ids.intersection(member_ids):
            await interaction.response.send_message(f"{E_CLOSED} Тільки персонал підтримки може взяти тікет.", ephemeral=True)
            return

        td = await self._get_ticket_data(interaction.channel.id)
        if td.get("claimed_by"):
            claimer = interaction.guild.get_member(td["claimed_by"])
            claimer_label = claimer.mention if claimer else "кимось"
            await interaction.response.send_message(f"{E_REASON} Тікет уже взятий {claimer_label}.", ephemeral=True)
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
    """Persistent view для публічної панелі."""

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
                label=bd["label"],
                emoji=emoji,
                style=bd.get("style", discord.ButtonStyle.blurple),
                custom_id=f"ticket_create_{i}_v2",
            )
            btn.callback = self._ticket_callback
            self.add_item(btn)

    async def _ticket_callback(self, interaction: discord.Interaction):
        await create_ticket_routine(interaction)


async def create_ticket_routine(interaction: discord.Interaction):
    guild = interaction.guild
    user = interaction.user
    config = await get_config(guild.id)

    category_id = config.get("category_id")
    category = guild.get_channel(category_id) if category_id else None
    if not category:
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            category = await guild.create_category("Tickets")

    channel_name = f"ticket-{user.name}".lower().replace(" ", "-")
    existing = discord.utils.get(guild.text_channels, name=channel_name, category_id=category.id)
    if existing:
        await interaction.response.send_message(f"{E_CLOSED} Відкритий тікет: {existing.mention}", ephemeral=True)
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
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"User ID: {user.id}",
        )
    except discord.HTTPException as exc:
        await interaction.response.send_message(f"{E_CLOSED} Помилка: {exc}", ephemeral=True)
        log.error(f"Failed to create ticket for {user}: {exc}")
        return

    ticket_id = await next_ticket_id(guild.id)
    opened_at = datetime.now(timezone.utc)

    await db.active_tickets.insert_one(
        {
            "channel_id": channel.id,
            "guild_id": guild.id,
            "ticket_id": ticket_id,
            "opened_by": user.id,
            "opened_at": opened_at,
            "claimed_by": None,
        }
    )

    await interaction.response.send_message(f"{E_OPENED} Тікет #{ticket_id}: {channel.mention}", ephemeral=True)

    embed = surface_embed("admin", "Тікет створено", tone="info")
    embed.set_author(name=guild.name)
    add_section(
        embed,
        "Старт",
        [
            compact_kv("Ticket ID", str(ticket_id)),
            compact_kv("Користувач", user.mention),
            compact_kv("Відкрито", _fmt_dt(opened_at)),
            "Опишіть проблему нижче — команда підтримки відповість у цьому каналі.",
        ],
    )
    set_surface_footer(embed, "admin", "Staff може взяти тікет у роботу або закрити його з причиною.")
    await channel.send(embed=embed, view=TicketControlView())


class TicketAdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.embed_title = "Служба підтримки"
        self.embed_desc = "Натисніть кнопку нижче, щоб зв'язатися з адміністрацією."
        self.custom_buttons: list = []
        self.target_channel_id: int | None = None

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.category],
        placeholder="Категорія для тікетів",
        min_values=0,
        max_values=1,
        row=0,
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        cat = select.values[0] if select.values else None
        await update_config(interaction.guild.id, {"category_id": cat.id if cat else None})
        label = cat.mention if cat else "Стандартна (Tickets)"
        await interaction.response.send_message(f"{E_OPENED} Категорія: {label}", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Лог-канал (закриті тікети)",
        min_values=0,
        max_values=1,
        row=1,
    )
    async def select_log_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        ch = select.values[0] if select.values else None
        await update_config(interaction.guild.id, {"log_channel_id": ch.id if ch else None})
        label = ch.mention if ch else "Відключено"
        await interaction.response.send_message(f"{E_OPENED} Лог-канал: {label}", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Канал для публікації панелі",
        min_values=0,
        max_values=1,
        row=2,
    )
    async def select_panel_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        ch = select.values[0] if select.values else None
        self.target_channel_id = ch.id if ch else None
        label = ch.mention if ch else "Поточний канал"
        await interaction.response.send_message(f"{E_OPENED} Панель буде надіслана в: {label}", ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Ролі підтримки",
        min_values=0,
        max_values=20,
        row=3,
    )
    async def select_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role_ids = [role.id for role in select.values]
        await update_config(interaction.guild.id, {"support_role_ids": role_ids})
        mentions = ", ".join(role.mention for role in select.values) or "Очищено"
        await interaction.response.send_message(f"{E_OPENED} Ролі підтримки: {mentions}", ephemeral=True)

    @discord.ui.button(label="Роль за ID", style=discord.ButtonStyle.secondary, row=4)
    async def add_role_id(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RoleInputModal())

    @discord.ui.button(label="Текст панелі", style=discord.ButtonStyle.secondary, row=4)
    async def edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PanelContentModal(self.embed_title, self.embed_desc)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.embed_title = modal.panel_title.value
        self.embed_desc = modal.panel_desc.value
        await interaction.edit_original_response(embed=self._build_preview())

    @discord.ui.button(label="Додати кнопку", style=discord.ButtonStyle.secondary, row=4)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.custom_buttons) >= 10:
            await interaction.response.send_message(f"{E_CLOSED} Максимум 10 кнопок.", ephemeral=True)
            return
        await interaction.response.send_modal(ButtonConfigModal(self))

    @discord.ui.button(
        label="Надіслати панель",
        emoji=discord.PartialEmoji.from_str(E_CLIPBOARD),
        style=discord.ButtonStyle.success,
        row=4,
    )
    async def send_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        target_ch = interaction.guild.get_channel(self.target_channel_id) if self.target_channel_id else interaction.channel
        if not target_ch:
            await interaction.response.send_message(f"{E_CLOSED} Канал не знайдено.", ephemeral=True)
            return

        try:
            final_view = DynamicTicketView(self.custom_buttons) if self.custom_buttons else TicketView()
            await target_ch.send(embed=self._build_preview(), view=final_view)
            await interaction.response.edit_message(
                content=f"{E_OPENED} Панель надіслана в {target_ch.mention}!",
                embed=None,
                view=None,
            )
        except discord.HTTPException as exc:
            await interaction.response.send_message(f"{E_CLOSED} Помилка: {exc}", ephemeral=True)

    def _build_preview(self) -> discord.Embed:
        return discord.Embed(title=self.embed_title, description=self.embed_desc, color=EMBED_COLOR)


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
        config = await get_config(interaction.guild.id)
        cat_id = config.get("category_id")
        log_id = config.get("log_channel_id")
        role_ids = config.get("support_role_ids", [])

        embed = surface_embed("admin", "Система тікетів", tone="info")
        add_section(
            embed,
            "Поточний стан",
            [
                compact_kv("Категорія", f"<#{cat_id}>" if cat_id else "Стандартна"),
                compact_kv("Лог-канал", f"<#{log_id}>" if log_id else "Не налаштовано"),
                compact_kv(
                    "Ролі підтримки",
                    ", ".join(f"<@&{role_id}>" for role_id in role_ids) if role_ids else "Не налаштовано",
                ),
                "Використовуй селектори нижче для повного налаштування панелі.",
            ],
        )
        set_surface_footer(embed, "admin", "Close summary і transcript працюють через той самий ticket pipeline.")
        await interaction.response.send_message(embed=embed, view=TicketAdminView(), ephemeral=True)


async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
