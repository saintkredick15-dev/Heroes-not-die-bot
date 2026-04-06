"""
Система тікетів:
- одна команда /ticket для адмін-налаштувань
- claim для staff workflow
- close через modal із причиною
- transcript txt/html у лог-канал під час закриття
- DM opener-у з підсумком закриття
"""

import asyncio
import html
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from modules.db import get_database
from modules.logger import Logger
from services.metrics import inc_global_metric
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
TICKET_CARD_COLOR = 0xF2F3F5
TRANSCRIPT_MAX_BYTES = 7_500_000
TRANSCRIPT_FORMATS = ("txt", "html", "both")


async def get_config(guild_id: int) -> dict:
    return await collection.find_one({"_id": guild_id}) or {}


async def update_config(guild_id: int, data: dict):
    await collection.update_one({"_id": guild_id}, {"$set": data}, upsert=True)


def normalize_transcript_format(value: str | None) -> str:
    if value in TRANSCRIPT_FORMATS:
        return value
    return "both"


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


def _ticket_card_embed(title: str, description: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=title, color=TICKET_CARD_COLOR)
    if description:
        embed.description = description
    return embed


def _build_panel_embed(title: str, description: str) -> discord.Embed:
    embed = _ticket_card_embed(title, description)
    return embed


def _serialize_button(button_data: dict) -> dict:
    style_raw = button_data.get("style", discord.ButtonStyle.blurple)
    if isinstance(style_raw, discord.ButtonStyle):
        style_value = style_raw.value
    else:
        try:
            style_value = discord.ButtonStyle(style_raw).value
        except Exception:
            style_value = discord.ButtonStyle.blurple.value
    return {
        "label": str(button_data.get("label") or "Тікет").strip() or "Тікет",
        "emoji": str(button_data.get("emoji") or "").strip() or None,
        "style": style_value,
    }


def _load_panel_buttons(config: dict) -> list[dict]:
    raw_buttons = config.get("panel_buttons", [])
    if not isinstance(raw_buttons, list):
        return []
    buttons: list[dict] = []
    for item in raw_buttons[:10]:
        if not isinstance(item, dict):
            continue
        buttons.append(_serialize_button(item))
    return buttons


@dataclass
class TicketWizardState:
    category_id: int | None = None
    log_channel_id: int | None = None
    support_role_ids: list[int] = field(default_factory=list)
    panel_title: str = "Служба підтримки"
    panel_desc: str = "Натисніть кнопку нижче, щоб зв'язатися з адміністрацією."
    panel_buttons: list[dict] = field(default_factory=list)
    panel_channel_id: int | None = None
    transcript_format: str = "both"

    @classmethod
    def from_config(cls, config: dict) -> "TicketWizardState":
        return cls(
            category_id=config.get("category_id"),
            log_channel_id=config.get("log_channel_id"),
            support_role_ids=[role_id for role_id in config.get("support_role_ids", []) if isinstance(role_id, int)],
            panel_title=str(config.get("panel_title") or "Служба підтримки"),
            panel_desc=str(config.get("panel_desc") or "Натисніть кнопку нижче, щоб зв'язатися з адміністрацією."),
            panel_buttons=_load_panel_buttons(config),
            panel_channel_id=config.get("panel_channel_id"),
            transcript_format=normalize_transcript_format(config.get("transcript_format")),
        )

    def as_config_patch(self) -> dict:
        return {
            "category_id": self.category_id,
            "log_channel_id": self.log_channel_id,
            "support_role_ids": list(self.support_role_ids),
            "panel_title": self.panel_title,
            "panel_desc": self.panel_desc,
            "panel_buttons": [dict(button) for button in self.panel_buttons],
            "panel_channel_id": self.panel_channel_id,
            "transcript_format": normalize_transcript_format(self.transcript_format),
        }


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


async def _collect_transcript_entries(channel: discord.TextChannel) -> list[dict]:
    entries: list[dict] = []
    async for message in channel.history(limit=None, oldest_first=True):
        avatar_url = None
        try:
            avatar_url = message.author.display_avatar.url
        except Exception:
            avatar_url = None

        entries.append(
            {
                "created_at": message.created_at,
                "author_display": getattr(message.author, "display_name", str(message.author)),
                "author_full": str(message.author),
                "author_id": getattr(message.author, "id", None),
                "avatar_url": avatar_url,
                "content": _safe_text(message.content),
                "attachments": [
                    {"filename": attachment.filename, "url": attachment.url}
                    for attachment in message.attachments
                ],
                "embeds_count": len(message.embeds),
                "stickers_count": len(message.stickers),
                "message_type": getattr(message.type, "name", str(message.type)),
            }
        )
    return entries


def _build_transcript_text(channel: discord.TextChannel, entries: list[dict]) -> str:
    lines = [
        f"Ticket transcript: #{channel.name}",
        f"Guild ID: {channel.guild.id}",
        f"Channel ID: {channel.id}",
        f"Generated at: {_fmt_dt(datetime.now(timezone.utc))}",
        "-" * 72,
    ]

    for entry in entries:
        created = _fmt_dt(entry["created_at"])
        author = f"{entry['author_full']} ({entry['author_id']})"
        lines.append(f"[{created}] {author}")

        if entry["content"]:
            lines.append(entry["content"])
        else:
            lines.append("[без тексту]")

        if entry["attachments"]:
            lines.append("Attachments:")
            for attachment in entry["attachments"]:
                lines.append(f"- {attachment['filename']}: {attachment['url']}")

        if entry["embeds_count"]:
            lines.append(f"[Embeds: {entry['embeds_count']}]")

        if entry["stickers_count"]:
            lines.append(f"[Stickers: {entry['stickers_count']}]")

        if entry["message_type"] not in {"default", "reply"}:
            lines.append(f"[Message type: {entry['message_type']}]")

        lines.append("")

    return "\n".join(lines)


def _html_escape_with_breaks(value: str | None) -> str:
    if not value:
        return ""
    return html.escape(value).replace("\n", "<br>")


def _render_transcript_html(
    *,
    guild: discord.Guild,
    channel: discord.TextChannel,
    ticket_id: int | str,
    opened_by: discord.Member | None,
    closed_by: discord.Member,
    opened_at: datetime | None,
    closed_at: datetime,
    claimed_by: discord.Member | None,
    reason: str,
    entries: list[dict],
) -> str:
    meta_rows = [
        ("Ticket ID", str(ticket_id)),
        ("Guild", guild.name),
        ("Channel", f"#{channel.name}"),
        ("Opened by", opened_by.display_name if opened_by else "Невідомо"),
        ("Claimed by", claimed_by.display_name if claimed_by else "Не взято"),
        ("Closed by", closed_by.display_name),
        ("Opened at", _fmt_dt(opened_at)),
        ("Closed at", _fmt_dt(closed_at)),
        ("Reason", reason),
    ]

    message_blocks: list[str] = []
    for entry in entries:
        content_html = _html_escape_with_breaks(entry["content"])
        attachment_html = ""
        if entry["attachments"]:
            items = "".join(
                f'<li><a href="{html.escape(item["url"], quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(item["filename"])}</a></li>'
                for item in entry["attachments"]
            )
            attachment_html = f'<div class="attachments"><div class="label">Attachments</div><ul>{items}</ul></div>'

        marker_bits: list[str] = []
        if entry["embeds_count"]:
            marker_bits.append(f"Embeds: {entry['embeds_count']}")
        if entry["stickers_count"]:
            marker_bits.append(f"Stickers: {entry['stickers_count']}")
        if entry["message_type"] not in {"default", "reply"}:
            marker_bits.append(f"Type: {entry['message_type']}")
        markers_html = "".join(f'<span class="chip">{html.escape(bit)}</span>' for bit in marker_bits)

        body_html = content_html or '<span class="empty">[без тексту]</span>'
        avatar_html = (
            f'<img class="avatar" src="{html.escape(entry["avatar_url"], quote=True)}" alt="avatar" />'
            if entry["avatar_url"]
            else '<div class="avatar avatar-fallback"></div>'
        )
        message_blocks.append(
            f"""
            <article class="message">
              {avatar_html}
              <div class="message-body">
                <div class="message-head">
                  <span class="author">{html.escape(entry["author_display"])}</span>
                  <span class="author-meta">{html.escape(entry["author_full"])}</span>
                  <span class="timestamp">{html.escape(_fmt_dt(entry["created_at"]))}</span>
                </div>
                <div class="content">{body_html}</div>
                {attachment_html}
                <div class="markers">{markers_html}</div>
              </div>
            </article>
            """
        )

    meta_html = "".join(
        f'<div class="meta-row"><span class="meta-key">{html.escape(key)}</span><span class="meta-value">{html.escape(value)}</span></div>'
        for key, value in meta_rows
    )

    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ticket #{html.escape(str(ticket_id))} Transcript</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #12141a;
      --panel: #1b1f27;
      --panel-soft: #232833;
      --border: #313847;
      --text: #f3f4f6;
      --muted: #9ca3af;
      --accent: #8ab4ff;
      --good: #22c55e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #101218 0%, #171b22 100%);
      color: var(--text);
      font-family: Inter, "Segoe UI", system-ui, sans-serif;
      line-height: 1.5;
    }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero, .meta, .timeline {{ background: rgba(27, 31, 39, 0.96); border: 1px solid var(--border); border-radius: 20px; }}
    .hero {{ padding: 28px; margin-bottom: 20px; }}
    .eyebrow {{ color: var(--accent); font-size: 12px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }}
    h1 {{ margin: 10px 0 8px; font-size: 34px; line-height: 1.1; }}
    .sub {{ color: var(--muted); margin: 0; }}
    .meta {{ padding: 18px 20px; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px 18px; margin-bottom: 20px; }}
    .meta-row {{ display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; background: rgba(255,255,255,0.02); border-radius: 14px; }}
    .meta-key {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
    .meta-value {{ font-size: 14px; word-break: break-word; }}
    .timeline {{ padding: 18px; }}
    .timeline-title {{ margin: 0 0 14px; font-size: 18px; }}
    .message {{ display: grid; grid-template-columns: 44px 1fr; gap: 14px; padding: 14px 10px; border-top: 1px solid rgba(255,255,255,0.05); }}
    .message:first-of-type {{ border-top: 0; }}
    .avatar {{ width: 44px; height: 44px; border-radius: 999px; object-fit: cover; background: #2d3340; }}
    .avatar-fallback {{ border: 1px solid rgba(255,255,255,0.08); }}
    .message-head {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; margin-bottom: 6px; }}
    .author {{ font-weight: 700; }}
    .author-meta, .timestamp {{ color: var(--muted); font-size: 13px; }}
    .content {{ white-space: normal; word-break: break-word; }}
    .attachments {{ margin-top: 10px; padding: 10px 12px; background: var(--panel-soft); border-radius: 12px; }}
    .attachments .label {{ color: var(--muted); font-size: 12px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .08em; }}
    .attachments ul {{ margin: 0; padding-left: 18px; }}
    .attachments a {{ color: var(--accent); text-decoration: none; }}
    .attachments a:hover {{ text-decoration: underline; }}
    .markers {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .chip {{ padding: 5px 9px; border-radius: 999px; background: rgba(138,180,255,0.12); color: var(--accent); font-size: 12px; }}
    .empty {{ color: var(--muted); font-style: italic; }}
    @media (max-width: 720px) {{
      .wrap {{ padding: 20px 14px 36px; }}
      h1 {{ font-size: 28px; }}
      .message {{ grid-template-columns: 1fr; }}
      .avatar {{ width: 36px; height: 36px; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="eyebrow">Ticket Transcript</div>
      <h1>#{html.escape(channel.name)} • Ticket #{html.escape(str(ticket_id))}</h1>
      <p class="sub">{html.escape(guild.name)} • Архів переписки після закриття тікета</p>
    </section>
    <section class="meta">
      {meta_html}
    </section>
    <section class="timeline">
      <h2 class="timeline-title">Повідомлення</h2>
      {''.join(message_blocks) if message_blocks else '<p class="empty">У цьому тікеті немає повідомлень.</p>'}
    </section>
  </main>
</body>
</html>"""


def _build_transcript_file(ticket_id: int | str, transcript_text: str) -> discord.File:
    payload = _truncate_transcript(transcript_text)
    filename = f"ticket-{ticket_id}-transcript.txt"
    return discord.File(io.BytesIO(payload), filename=filename)


def _truncate_html_transcript(html_text: str, transcript_text: str) -> bytes:
    data = html_text.encode("utf-8")
    if len(data) <= TRANSCRIPT_MAX_BYTES:
        return data

    notice = "HTML transcript обрізано, бо файл перевищив ліміт Discord."
    escaped_text = html.escape(transcript_text)
    prefix = f"""<!DOCTYPE html>
<html lang="uk">
<head><meta charset="utf-8"><title>Transcript truncated</title></head>
<body style="font-family:Inter,Segoe UI,sans-serif;background:#111827;color:#f3f4f6;padding:24px;">
  <h1>Transcript truncated</h1>
  <p>{html.escape(notice)}</p>
  <pre style="white-space:pre-wrap;word-break:break-word;background:#1f2937;padding:16px;border-radius:12px;">"""
    suffix = "</pre></body></html>"
    prefix_bytes = prefix.encode("utf-8")
    suffix_bytes = suffix.encode("utf-8")
    allowed = max(0, TRANSCRIPT_MAX_BYTES - len(prefix_bytes) - len(suffix_bytes))
    return prefix_bytes + escaped_text.encode("utf-8")[:allowed] + suffix_bytes.encode("utf-8")


def _build_transcript_html_file(ticket_id: int | str, transcript_html: str, transcript_text: str) -> discord.File:
    payload = _truncate_html_transcript(transcript_html, transcript_text)
    filename = f"ticket-{ticket_id}-transcript.html"
    return discord.File(io.BytesIO(payload), filename=filename)


def _build_transcript_files(
    ticket_id: int | str,
    transcript_format: str,
    transcript_text: str,
    transcript_html: str,
) -> list[discord.File]:
    normalized = normalize_transcript_format(transcript_format)
    files: list[discord.File] = []
    if normalized in {"txt", "both"}:
        files.append(_build_transcript_file(ticket_id, transcript_text))
    if normalized in {"html", "both"}:
        files.append(_build_transcript_html_file(ticket_id, transcript_html, transcript_text))
    return files


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
    embed = _ticket_card_embed("Тікет закрито")
    embed.timestamp = closed_at
    embed.add_field(name=f"{E_CLIPBOARD} Ticket ID", value=str(ticket_id), inline=False)
    embed.add_field(name=f"{E_OPENED} Відкрив", value=_member_label(opened_by, "Невідомо"), inline=False)
    embed.add_field(name=f"{E_CLAIMED} Взяв", value=_member_label(claimed_by, "Не взято"), inline=False)
    embed.add_field(name=f"{E_CLOSED} Закрив", value=closed_by.mention, inline=False)
    embed.add_field(name=f"{E_CLOCK} Відкрито", value=_fmt_dt(opened_at), inline=False)
    embed.add_field(name=f"{E_CLOCK} Закрито", value=_fmt_dt(closed_at), inline=False)
    embed.add_field(name=f"{E_REASON} Причина", value=reason, inline=False)
    return embed


def _build_open_embed(ticket_id: int | str, user: discord.Member, opened_at: datetime) -> discord.Embed:
    embed = _ticket_card_embed(
        "Тікет створено",
        "Опишіть проблему нижче. Команда підтримки відповість у цьому каналі.",
    )
    embed.add_field(name=f"{E_CLIPBOARD} ID тікета", value=str(ticket_id), inline=False)
    embed.add_field(name=f"{E_OPENED} Відкрив", value=user.mention, inline=False)
    embed.add_field(name=f"{E_CLOCK} Час відкриття", value=_fmt_dt(opened_at), inline=False)
    return embed


def _build_claim_embed(ticket_id: int | str, claimer: discord.Member) -> discord.Embed:
    embed = _ticket_card_embed("Тікет взято в роботу")
    embed.add_field(name="Ticket ID", value=str(ticket_id), inline=False)
    embed.add_field(name="Працівник", value=claimer.mention, inline=False)
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

    config = await get_config(guild.id)
    log_ch_id = config.get("log_channel_id")
    transcript_format = normalize_transcript_format(config.get("transcript_format"))
    transcript_logged = False
    transcript_issue = False
    if log_ch_id:
        log_ch = guild.get_channel(log_ch_id)
        if log_ch:
            try:
                transcript_entries = await _collect_transcript_entries(channel)
                transcript_text = _build_transcript_text(channel, transcript_entries)
                transcript_html = _render_transcript_html(
                    guild=guild,
                    channel=channel,
                    ticket_id=ticket_id,
                    opened_by=opened_by,
                    closed_by=closed_by,
                    opened_at=opened_at,
                    closed_at=closed_at,
                    claimed_by=claimed_by,
                    reason=reason,
                    entries=transcript_entries,
                )
                transcript_files = _build_transcript_files(ticket_id, transcript_format, transcript_text, transcript_html)
                await log_ch.send(embed=embed, files=transcript_files)
                transcript_logged = True
            except Exception:
                transcript_issue = True
                log.warning(f"Failed to send ticket transcript to log channel {log_ch_id} in guild {guild.id}")
        else:
            transcript_issue = True

    if opened_by:
        try:
            await opened_by.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    notice = "Тікет буде закрито через 5 секунд."
    if transcript_logged:
        notice += " Підсумок і транскрипт надіслано в лог-канал."
    elif log_ch_id:
        notice += " Не вдалося надіслати transcript у лог-канал."
    elif transcript_issue:
        notice += " Не вдалося надіслати transcript у лог-канал."
    await interaction.response.send_message(notice, ephemeral=True)
    await inc_global_metric("tickets_closed_total")

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


class RoleInputModal(discord.ui.Modal, title="Додати роль підтримки"):
    role_id = discord.ui.TextInput(label="ID ролі", placeholder="Наприклад: 123456789012345678")

    def __init__(self):
        super().__init__()
        self.result_role_id: int | None = None

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.result_role_id = int(self.role_id.value.strip())
        except ValueError:
            await interaction.response.send_message(f"{E_CLOSED} Невірний формат ID.", ephemeral=True)
            self.stop()
            return
        await interaction.response.defer()
        self.stop()


class PanelContentModal(discord.ui.Modal, title="Текст панелі"):
    panel_title = discord.ui.TextInput(label="Заголовок", default="Служба підтримки")
    panel_desc = discord.ui.TextInput(
        label="Опис",
        style=discord.TextStyle.paragraph,
        default="Натисніть кнопку нижче, щоб зв'язатися з адміністрацією.",
    )

    def __init__(self, current_title: str, current_desc: str):
        super().__init__()
        self.result_title: str | None = None
        self.result_desc: str | None = None
        self.panel_title.default = current_title
        self.panel_desc.default = current_desc

    async def on_submit(self, interaction: discord.Interaction):
        self.result_title = self.panel_title.value.strip() or "Служба підтримки"
        self.result_desc = self.panel_desc.value.strip() or "Натисніть кнопку нижче, щоб зв'язатися з адміністрацією."
        await interaction.response.defer()
        self.stop()


class ButtonConfigModal(discord.ui.Modal, title="Додати кнопку"):
    btn_label = discord.ui.TextInput(label="Текст кнопки", placeholder="Створити тікет")
    btn_emoji = discord.ui.TextInput(label="Emoji (необов'язково)", required=False, placeholder=E_TICKET)

    def __init__(self):
        super().__init__()
        self.result_button: dict | None = None

    async def on_submit(self, interaction: discord.Interaction):
        label = self.btn_label.value.strip() or "Тікет"
        emoji_str = self.btn_emoji.value.strip() or None
        self.result_button = _serialize_button(
            {
                "label": label,
                "emoji": emoji_str,
                "style": discord.ButtonStyle.blurple.value,
            }
        )
        await interaction.response.defer()
        self.stop()


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
        embed = _build_claim_embed(td.get("ticket_id", "?"), interaction.user)
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
            button_data = _serialize_button(bd)
            emoji = None
            if button_data.get("emoji"):
                try:
                    emoji = discord.PartialEmoji.from_str(button_data["emoji"])
                except Exception:
                    emoji = None

            btn = discord.ui.Button(
                label=button_data["label"],
                emoji=emoji,
                style=discord.ButtonStyle(button_data.get("style", discord.ButtonStyle.blurple.value)),
                custom_id=f"ticket_create_{i}_v2",
            )
            btn.callback = self._ticket_callback
            self.add_item(btn)

    async def _ticket_callback(self, interaction: discord.Interaction):
        await create_ticket_routine(interaction)


class TicketPanelButtonsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for index in range(10):
            button = discord.ui.Button(
                label=f"Тікет {index + 1}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ticket_create_{index}_v2",
            )
            button.callback = self._ticket_callback
            self.add_item(button)

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
    await inc_global_metric("tickets_opened_total")

    await interaction.response.send_message(f"{E_OPENED} Тікет #{ticket_id}: {channel.mention}", ephemeral=True)

    embed = _build_open_embed(ticket_id, user, opened_at)
    await channel.send(embed=embed, view=TicketControlView())


class TicketWizardStepButton(discord.ui.Button):
    def __init__(self, label: str, target_step: str, row: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.target_step = target_step

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        new_view = TicketWizardView(view.state, self.target_step)
        await interaction.response.edit_message(embed=new_view.build_embed(interaction.guild), view=new_view)


class TicketCategorySelect(discord.ui.ChannelSelect):
    def __init__(self, state: TicketWizardState):
        defaults = [discord.Object(id=state.category_id)] if state.category_id else []
        super().__init__(
            placeholder="Категорія для тікетів",
            channel_types=[discord.ChannelType.category],
            min_values=0,
            max_values=1,
            row=0,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        category = self.values[0] if self.values else None
        view.state.category_id = category.id if category else None
        await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.response.edit_message(embed=new_view.build_embed(interaction.guild), view=new_view)


class TicketLogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, state: TicketWizardState):
        defaults = [discord.Object(id=state.log_channel_id)] if state.log_channel_id else []
        super().__init__(
            placeholder="Лог-канал для закритих тікетів",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=1,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        channel = self.values[0] if self.values else None
        view.state.log_channel_id = channel.id if channel else None
        await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.response.edit_message(embed=new_view.build_embed(interaction.guild), view=new_view)


class TicketTranscriptFormatSelect(discord.ui.Select):
    def __init__(self, state: TicketWizardState):
        current = normalize_transcript_format(state.transcript_format)
        options = [
            discord.SelectOption(label="TXT only", value="txt", description="Лише plain-text transcript", default=current == "txt"),
            discord.SelectOption(label="HTML only", value="html", description="Лише HTML transcript", default=current == "html"),
            discord.SelectOption(label="TXT + HTML", value="both", description="Надсилати обидва файли", default=current == "both"),
        ]
        super().__init__(placeholder="Формат transcript", min_values=1, max_values=1, row=2, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        view.state.transcript_format = normalize_transcript_format(self.values[0])
        await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.response.edit_message(embed=new_view.build_embed(interaction.guild), view=new_view)


class TicketSupportRoleSelect(discord.ui.RoleSelect):
    def __init__(self, state: TicketWizardState):
        defaults = [discord.Object(id=role_id) for role_id in state.support_role_ids[:25]]
        super().__init__(
            placeholder="Ролі підтримки",
            min_values=0,
            max_values=20,
            row=0,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        view.state.support_role_ids = [role.id for role in self.values]
        await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.response.edit_message(embed=new_view.build_embed(interaction.guild), view=new_view)


class TicketPanelChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, state: TicketWizardState):
        defaults = [discord.Object(id=state.panel_channel_id)] if state.panel_channel_id else []
        super().__init__(
            placeholder="Канал для публікації панелі",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        channel = self.values[0] if self.values else None
        view.state.panel_channel_id = channel.id if channel else None
        await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.response.edit_message(embed=new_view.build_embed(interaction.guild), view=new_view)


class TicketRoleIdButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Додати роль за ID", emoji=discord.PartialEmoji.from_str(E_SUPPORTROLE), style=discord.ButtonStyle.secondary, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        modal = RoleInputModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result_role_id is None:
            return

        role = interaction.guild.get_role(modal.result_role_id)
        if not role:
            try:
                role = await interaction.guild.fetch_role(modal.result_role_id)
            except (discord.NotFound, discord.HTTPException):
                role = None
        if not role:
            await interaction.followup.send(f"{E_CLOSED} Роль `{modal.result_role_id}` не знайдено.", ephemeral=True)
            return

        if role.id not in view.state.support_role_ids:
            view.state.support_role_ids.append(role.id)
            await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.edit_original_response(embed=new_view.build_embed(interaction.guild), view=new_view)
        await interaction.followup.send(f"{E_OPENED} Роль {role.mention} додана.", ephemeral=True)


class TicketPanelTextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Текст панелі", emoji=discord.PartialEmoji.from_str(E_CLIPBOARD), style=discord.ButtonStyle.secondary, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        modal = PanelContentModal(view.state.panel_title, view.state.panel_desc)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result_title is None or modal.result_desc is None:
            return
        view.state.panel_title = modal.result_title
        view.state.panel_desc = modal.result_desc
        await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.edit_original_response(embed=new_view.build_embed(interaction.guild), view=new_view)
        await interaction.followup.send(f"{E_OPENED} Текст панелі оновлено.", ephemeral=True)


class TicketAddPanelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Додати кнопку", emoji=discord.PartialEmoji.from_str(E_TICKET), style=discord.ButtonStyle.secondary, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        if len(view.state.panel_buttons) >= 10:
            await interaction.response.send_message(f"{E_CLOSED} Максимум 10 кнопок.", ephemeral=True)
            return

        modal = ButtonConfigModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result_button is None:
            return
        view.state.panel_buttons.append(modal.result_button)
        await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.edit_original_response(embed=new_view.build_embed(interaction.guild), view=new_view)
        await interaction.followup.send(f"{E_OPENED} Кнопку «{modal.result_button['label']}» додано.", ephemeral=True)


class TicketResetPanelButtonsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Скинути кнопки", emoji=discord.PartialEmoji.from_str(E_DELETE), style=discord.ButtonStyle.danger, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        view.state.panel_buttons = []
        await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.response.edit_message(embed=new_view.build_embed(interaction.guild), view=new_view)


class TicketPublishPanelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Надіслати панель", emoji=discord.PartialEmoji.from_str(E_CLIPBOARD), style=discord.ButtonStyle.success, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "TicketWizardView" = self.view
        target_channel = interaction.guild.get_channel(view.state.panel_channel_id) if view.state.panel_channel_id else interaction.channel
        if not target_channel:
            await interaction.response.send_message(f"{E_CLOSED} Канал для публікації не знайдено.", ephemeral=True)
            return

        try:
            final_view = DynamicTicketView(view.state.panel_buttons) if view.state.panel_buttons else TicketView()
            await target_channel.send(embed=_build_panel_embed(view.state.panel_title, view.state.panel_desc), view=final_view)
        except discord.HTTPException as exc:
            await interaction.response.send_message(f"{E_CLOSED} Помилка: {exc}", ephemeral=True)
            return

        await update_config(interaction.guild.id, view.state.as_config_patch())
        new_view = TicketWizardView(view.state, view.step)
        await interaction.response.edit_message(embed=new_view.build_embed(interaction.guild), view=new_view)
        await interaction.followup.send(f"{E_OPENED} Панель надіслана в {target_channel.mention}.", ephemeral=True)


class TicketWizardView(discord.ui.View):
    STEPS = (
        ("basic", "Основне"),
        ("team", "Команда"),
        ("panel", "Панель"),
        ("publish", "Публікація"),
    )

    def __init__(self, state: TicketWizardState, step: str = "basic"):
        super().__init__(timeout=600)
        self.state = state
        self.step = step if step in {key for key, _ in self.STEPS} else "basic"
        self._build_items()

    def _step_index(self) -> int:
        return next(index for index, (key, _) in enumerate(self.STEPS) if key == self.step)

    def _step_label(self) -> str:
        return next(label for key, label in self.STEPS if key == self.step)

    def _build_items(self):
        if self.step == "basic":
            self.add_item(TicketCategorySelect(self.state))
            self.add_item(TicketLogChannelSelect(self.state))
            self.add_item(TicketTranscriptFormatSelect(self.state))
        elif self.step == "team":
            self.add_item(TicketSupportRoleSelect(self.state))
            self.add_item(TicketRoleIdButton())
        elif self.step == "panel":
            self.add_item(TicketPanelTextButton())
            self.add_item(TicketAddPanelButton())
            self.add_item(TicketResetPanelButtonsButton())
        elif self.step == "publish":
            self.add_item(TicketPanelChannelSelect(self.state))
            self.add_item(TicketPublishPanelButton())

        step_index = self._step_index()
        if step_index > 0:
            prev_step = self.STEPS[step_index - 1][0]
            self.add_item(TicketWizardStepButton("← Назад", prev_step, row=4))
        if step_index < len(self.STEPS) - 1:
            next_step = self.STEPS[step_index + 1][0]
            self.add_item(TicketWizardStepButton("Далі →", next_step, row=4))

    def build_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = surface_embed(
            "admin",
            f"{E_TICKET} Тікет сетап",
            f"Крок {self._step_index() + 1}/4 — {self._step_label()}",
        )

        category_label = f"<#{self.state.category_id}>" if self.state.category_id else "Стандартна (Tickets)"
        log_label = f"<#{self.state.log_channel_id}>" if self.state.log_channel_id else "Не налаштовано"
        panel_channel = f"<#{self.state.panel_channel_id}>" if self.state.panel_channel_id else "Поточний канал"
        roles_label = ", ".join(f"<@&{role_id}>" for role_id in self.state.support_role_ids) if self.state.support_role_ids else "Не налаштовано"
        transcript_label = {
            "txt": "txt",
            "html": "html",
            "both": "txt + html",
        }.get(normalize_transcript_format(self.state.transcript_format), "txt + html")

        add_section(
            embed,
            "Поточний стан",
            [
                compact_kv(f"{E_TICKET} Категорія", category_label),
                compact_kv(f"{E_CLIPBOARD} Лог-канал", log_label),
                compact_kv("Формат transcript", transcript_label),
                compact_kv(f"{E_SUPPORTROLE} Ролі підтримки", roles_label),
                compact_kv("Кнопки панелі", str(len(self.state.panel_buttons) or 1)),
                compact_kv("Канал публікації", panel_channel),
            ],
        )

        if self.step == "basic":
            add_section(embed, "Що налаштовується", ["Категорія для нових тікетів.", "Канал, куди надсилається підсумок закриття і transcript.", "Формат archive transcript: txt, html або обидва."])
        elif self.step == "team":
            add_section(embed, "Що налаштовується", ["Ролі, які можуть брати і закривати тікети.", "За потреби роль можна додати вручну через ID."])
        elif self.step == "panel":
            button_lines = [f"• {button['label']}" for button in self.state.panel_buttons[:10]] or ["• Стандартна кнопка «Створити тікет»"]
            add_section(
                embed,
                "Панель",
                [
                    compact_kv("Заголовок", self.state.panel_title),
                    compact_kv("Опис", self.state.panel_desc),
                    "Кнопки:",
                    *button_lines,
                ],
            )
        elif self.step == "publish":
            add_section(
                embed,
                "Публікація",
                [
                    compact_kv("Канал", panel_channel),
                    compact_kv("Заголовок", self.state.panel_title),
                    compact_kv("Опис", self.state.panel_desc),
                    compact_kv("Кнопки", ", ".join(button["label"] for button in self.state.panel_buttons[:5]) if self.state.panel_buttons else "Стандартна кнопка"),
                ],
            )

        set_surface_footer(embed, "admin", "Налаштуйте крок і переходьте далі.")
        return embed


class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketPanelButtonsView())
        self.bot.add_view(TicketControlView())
        await collection.create_index("_id")
        await db.active_tickets.create_index("channel_id", unique=True, background=True)
        await db.active_tickets.create_index("guild_id", background=True)
        log.info("Ticket persistent views registered")

    @app_commands.command(name="ticket_setup", description="Налаштування системи тікетів")
    @app_commands.default_permissions(administrator=True)
    async def ticket_admin(self, interaction: discord.Interaction):
        config = await get_config(interaction.guild.id)
        state = TicketWizardState.from_config(config)
        view = TicketWizardView(state, "basic")
        await interaction.response.send_message(embed=view.build_embed(interaction.guild), view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
