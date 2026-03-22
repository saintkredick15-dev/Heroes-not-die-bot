from __future__ import annotations

import discord

from config.constants import Colors, Emojis

SURFACE_COLORS = {
    "admin": Colors.DARK.value,
    "navigation": 0x1F2636,
    "gameplay": 0x223041,
}

OUTCOME_COLORS = {
    "base": None,
    "success": Colors.SUCCESS.value,
    "error": Colors.ERROR.value,
    "warning": Colors.WARNING.value,
    "info": Colors.INFO.value,
}

SURFACE_FOOTERS = {
    "admin": "Огляд зверху, зміни нижче.",
    "navigation": "Обирайте модуль або дію нижче.",
    "gameplay": "Стислий статус зверху, деталі нижче.",
}


def surface_embed(
    surface: str,
    title: str,
    description: str | None = None,
    *,
    tone: str = "base",
) -> discord.Embed:
    color = OUTCOME_COLORS.get(tone) or SURFACE_COLORS.get(surface, Colors.DARK.value)
    return discord.Embed(title=title, description=description or None, color=color)


def add_section(
    embed: discord.Embed,
    name: str,
    lines: str | list[str],
    *,
    inline: bool = False,
) -> discord.Embed:
    if isinstance(lines, str):
        value = lines.strip() or "\u200b"
    else:
        value = "\n".join(line for line in lines if line).strip() or "\u200b"
    embed.add_field(name=name, value=value, inline=inline)
    return embed


def set_surface_footer(
    embed: discord.Embed,
    surface: str,
    text: str | None = None,
) -> discord.Embed:
    embed.set_footer(text=text or SURFACE_FOOTERS.get(surface, ""))
    return embed


def status_badge(enabled: bool) -> str:
    icon = Emojis.CHECK.value if enabled else Emojis.CROSS.value
    return f"{icon} {'Увімкнено' if enabled else 'Вимкнено'}"


def compact_kv(label: str, value: str) -> str:
    return f"**{label}:** {value}"


def bullet_list(items: list[str], prefix: str = "• ") -> str:
    return "\n".join(f"{prefix}{item}" for item in items if item)


def gameplay_result_embed(
    title: str,
    summary: str,
    *,
    tone: str,
    details: list[str] | None = None,
    footer: str | None = None,
) -> discord.Embed:
    embed = surface_embed("gameplay", title, summary, tone=tone)
    if details:
        add_section(embed, "Деталі", details, inline=False)
    return set_surface_footer(embed, "gameplay", footer)
