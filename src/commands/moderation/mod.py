"""
mod.py
Єдиний файл для moderation команд: warn, unwarn, warns, warnings, purge, mute, unmute, kick, ban.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from modules.db import get_database
from services.moderation import (
    ModerationActionError,
    apply_case,
    validate_moderation_target,
    _warn_case_state,
)

EMBED_COLOR = 0x1A1A2E
_CONFIG_PATH = Path(__file__).parents[3] / "config.json"

db = get_database()
E_CHECK = "<:check:1485597845883981905>"
E_HAMMER = "<:hammer:1485606127696609412>"
E_MUTE = "<:mute:1485607049504227369>"
E_KICK = "<:kick:1485607557291704341>"
E_BAN = "<:ban:1485607222414282822>"
E_TYPING = "<:typing_keyboard:1485717155080175616>"
E_WARN = "<:warning:1485598476850040843>"

UNIT_MAP = {"s": 1, "m": 60, "h": 3600, "d": 86400}
WARN_STATE_LABELS = {
    "active": "Активний",
    "decayed": "Спав",
    "revoked": "Знято",
}


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def check_permissions(interaction: discord.Interaction) -> bool:
    config = _load_config()
    return interaction.user.guild_permissions.administrator or interaction.user.id in config.get("dev", [])


def _ok(description: str) -> discord.Embed:
    return discord.Embed(description=description, color=EMBED_COLOR)


def _err(description: str) -> discord.Embed:
    return discord.Embed(
        description=f"<:close:1485598320935174317> {description}",
        color=0x2B2D31,
    )


def _parse_duration(text: str) -> int | None:
    text = text.strip().lower()
    if not text:
        return None
    suffix = text[-1]
    if suffix not in UNIT_MAP:
        return None
    try:
        return int(text[:-1]) * UNIT_MAP[suffix]
    except ValueError:
        return None


def _build_origin_text(interaction: discord.Interaction, command_name: str) -> str:
    channel_name = getattr(interaction.channel, "name", None)
    if channel_name:
        return f"Команда /{command_name} у #{channel_name}"
    return f"Команда /{command_name}"


def _build_warns_embed(
    *,
    member: discord.Member | discord.User,
    warns: list[dict],
    decay_days: int,
    self_view: bool,
) -> discord.Embed:
    title = "Твої попередження" if self_view else "Історія попереджень"
    description = "Активні, зняті та попередні варни у цьому сервері." if self_view else f"Користувач: {member.mention}"
    embed = discord.Embed(
        title=f"{E_WARN} {title}",
        description=description,
        color=EMBED_COLOR,
    )

    if not warns:
        embed.add_field(
            name="Результат",
            value="<:close:1485598320935174317> Попереджень не знайдено.",
            inline=False,
        )
        return embed

    active_count = 0
    revoked_count = 0
    decayed_count = 0

    for warn in warns:
        ts = warn.get("timestamp")
        ts_str = discord.utils.format_dt(ts, "R") if ts else "невідомо"
        reason = warn.get("reason", "Не вказано")
        moderator_id = warn.get("moderator_id")
        case_id = warn.get("case_id", "???")

        state = _warn_case_state(warn, decay_days)
        if state == "active":
            active_count += 1
        elif state == "revoked":
            revoked_count += 1
        else:
            decayed_count += 1

        moderator_text = f"<@{moderator_id}>" if moderator_id else "Система"
        value_lines = [
            f"**Статус:** {WARN_STATE_LABELS[state]}",
            f"**Причина:** {reason}",
            f"**Модератор:** {moderator_text}",
        ]
        if state == "revoked":
            revoked_at = warn.get("revoked_at")
            if revoked_at:
                value_lines.append(f"**Знято:** {discord.utils.format_dt(revoked_at, 'R')}")
            revoked_by = warn.get("revoked_by")
            if revoked_by:
                value_lines.append(f"**Хто зняв:** <@{revoked_by}>")
            revoke_reason = warn.get("revoke_reason")
            if revoke_reason:
                value_lines.append(f"**Причина зняття:** {revoke_reason}")

        embed.add_field(
            name=f"#{case_id} — {ts_str}",
            value="\n".join(value_lines),
            inline=False,
        )

    footer = f"Активних: {active_count} • Знятих: {revoked_count} • Загалом: {len(warns)}"
    if decayed_count:
        footer += f" • Спало: {decayed_count}"
    if decay_days > 0:
        footer += f" • decay: {decay_days} дн."
    embed.set_footer(text=footer)
    return embed


async def _fetch_warn_history(guild_id: int, user_id: int, limit: int = 20) -> tuple[list[dict], int]:
    settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
    decay_days = settings.get("warn_decay_days", 0)
    cursor = db.cases.find(
        {
            "guild_id": guild_id,
            "user_id": user_id,
            "action": "warn",
        }
    ).sort("timestamp", -1).limit(limit)
    warns = await cursor.to_list(length=limit)
    return warns, decay_days


def _manual_target_error(interaction: discord.Interaction, member: discord.Member, action: str) -> str | None:
    return validate_moderation_target(
        guild=interaction.guild,
        actor=interaction.user,
        target=member,
        action=action,
    )


class CustomPurgeModal(discord.ui.Modal, title="Свій термін видалення"):
    period = discord.ui.TextInput(
        label="Термін",
        placeholder="Наприклад: 10m, 2h, 3d, 30s",
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        seconds = _parse_duration(self.period.value)
        if not seconds or seconds <= 0:
            await interaction.response.send_message(
                embed=_err("Невірний формат. Приклади: `10m`, `2h`, `3d`"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        cutoff = discord.utils.utcnow() - datetime.timedelta(seconds=seconds)
        try:
            deleted = await interaction.channel.purge(after=cutoff)
            await interaction.followup.send(
                embed=_ok(f"<:trash:1485598963590758420> Видалено **{len(deleted)}** повідомлень."),
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(embed=_err("Немає прав на видалення."), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=_err(f"Помилка: {exc}"), ephemeral=True)


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await db.cases.create_index(
            [("guild_id", 1), ("case_id", 1)],
            unique=True,
            background=True,
        )
        await db.cases.create_index(
            [("guild_id", 1), ("user_id", 1), ("action", 1), ("timestamp", -1)],
            background=True,
        )

    @app_commands.command(name="warn", description="Видати попередження")
    @app_commands.describe(member="Кого попередити", reason="Причина варну")
    @app_commands.default_permissions(administrator=True)
    async def warn_cmd(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        target_error = _manual_target_error(interaction, member, "warn")
        if target_error:
            return await interaction.response.send_message(embed=_err(target_error), ephemeral=True)

        await interaction.response.defer()
        try:
            case_id = await apply_case(
                bot=self.bot,
                guild=interaction.guild,
                user=member,
                moderator=interaction.user,
                action="warn",
                reason=reason,
                source="manual",
                origin_text=_build_origin_text(interaction, "warn"),
            )
        except ModerationActionError as exc:
            return await interaction.followup.send(embed=_err(exc.user_message), ephemeral=True)

        await interaction.followup.send(embed=_ok(f"{E_HAMMER} {member.mention} отримав попередження. ID `#{case_id}`."))

    @app_commands.command(name="unwarn", description="Зняти попередження за Case ID")
    @app_commands.describe(member="У кого зняти попередження", case_id="Case ID попередження", reason="Причина зняття")
    @app_commands.default_permissions(administrator=True)
    async def unwarn_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        case_id: str,
        reason: str | None = None,
    ):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        case = await db.cases.find_one(
            {
                "guild_id": interaction.guild.id,
                "user_id": member.id,
                "action": "warn",
                "case_id": case_id.strip().lstrip("#"),
            }
        )
        if not case:
            return await interaction.followup.send(
                embed=_err("Warn case з таким ID для цього користувача не знайдено."),
                ephemeral=True,
            )
        if case.get("revoked") is True:
            return await interaction.followup.send(
                embed=_err("Це попередження вже знято."),
                ephemeral=True,
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        await db.cases.update_one(
            {"_id": case["_id"]},
            {
                "$set": {
                    "revoked": True,
                    "revoked_by": interaction.user.id,
                    "revoked_at": now,
                    "revoke_reason": (reason or "").strip() or None,
                }
            },
        )
        await interaction.followup.send(
            embed=_ok(f"{E_CHECK} Попередження `#{case['case_id']}` для {member.mention} знято."),
            ephemeral=True,
        )

    @app_commands.command(name="warnings", description="Переглянути свої попередження")
    async def warnings_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        warns, decay_days = await _fetch_warn_history(interaction.guild.id, interaction.user.id)
        embed = _build_warns_embed(member=interaction.user, warns=warns, decay_days=decay_days, self_view=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="warns", description="Переглянути історію попереджень користувача")
    @app_commands.describe(member="Чию історію переглянути")
    @app_commands.default_permissions(administrator=True)
    async def warns_cmd(self, interaction: discord.Interaction, member: discord.Member):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        warns, decay_days = await _fetch_warn_history(interaction.guild.id, member.id)
        embed = _build_warns_embed(member=member, warns=warns, decay_days=decay_days, self_view=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="purge", description="Очистити чат")
    @app_commands.describe(period="За який час видалити")
    @app_commands.choices(
        period=[
            app_commands.Choice(name="Всі повідомлення", value="all"),
            app_commands.Choice(name="Останні 24 години", value="1d"),
            app_commands.Choice(name="Останні 3 дні", value="3d"),
            app_commands.Choice(name="Останній тиждень", value="7d"),
            app_commands.Choice(name=f"{E_TYPING} Свій час (5m, 2h, 1d...)", value="custom"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def purge_cmd(self, interaction: discord.Interaction, period: app_commands.Choice[str]):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        if period.value == "custom":
            return await interaction.response.send_modal(CustomPurgeModal())

        await interaction.response.defer(ephemeral=True)
        try:
            if period.value == "all":
                deleted = await interaction.channel.purge()
            else:
                days = {"1d": 1, "3d": 3, "7d": 7}.get(period.value)
                cutoff = discord.utils.utcnow() - datetime.timedelta(days=days)
                deleted = await interaction.channel.purge(after=cutoff)
            await interaction.followup.send(
                embed=_ok(f"<:trash:1485598963590758420> Видалено **{len(deleted)}** повідомлень."),
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.followup.send(embed=_err(f"Помилка: {exc}"), ephemeral=True)

    @app_commands.command(name="mute", description="Тимчасово заглушити користувача (timeout)")
    @app_commands.describe(member="Кого заглушити", duration="Тривалість: 10m, 1h, 1d", reason="Причина")
    @app_commands.default_permissions(administrator=True)
    async def mute_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: str = "Не вказано",
    ):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        target_error = _manual_target_error(interaction, member, "mute")
        if target_error:
            return await interaction.response.send_message(embed=_err(target_error), ephemeral=True)

        seconds = _parse_duration(duration)
        if not seconds or seconds <= 0:
            return await interaction.response.send_message(
                embed=_err("Невірний формат. Приклад: `10m`, `1h`."),
                ephemeral=True,
            )

        await interaction.response.defer()
        try:
            case_id = await apply_case(
                bot=self.bot,
                guild=interaction.guild,
                user=member,
                moderator=interaction.user,
                action="mute",
                reason=reason,
                duration_seconds=seconds,
                source="manual",
                origin_text=_build_origin_text(interaction, "mute"),
            )
        except ModerationActionError as exc:
            return await interaction.followup.send(embed=_err(exc.user_message), ephemeral=True)

        await interaction.followup.send(
            embed=_ok(f"{E_MUTE} {member.mention} отримав тайм-аут на **{duration}**. ID `#{case_id}`.")
        )

    @app_commands.command(name="unmute", description="Зняти тайм-аут з користувача")
    @app_commands.describe(member="З кого зняти заглушення")
    @app_commands.default_permissions(administrator=True)
    async def unmute_cmd(self, interaction: discord.Interaction, member: discord.Member):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        target_error = _manual_target_error(interaction, member, "mute")
        if target_error:
            return await interaction.response.send_message(embed=_err(target_error), ephemeral=True)
        if not member.is_timed_out():
            return await interaction.response.send_message(
                embed=_err("У цього користувача зараз немає активного тайм-ауту."),
                ephemeral=True,
            )

        bot_member = interaction.guild.me
        if bot_member is None or not bot_member.guild_permissions.moderate_members:
            return await interaction.response.send_message(embed=_err("Боту бракує права `Moderate Members`."), ephemeral=True)
        if member.top_role >= bot_member.top_role:
            return await interaction.response.send_message(
                embed=_err("Бот не може зняти тайм-аут через рольову ієрархію."),
                ephemeral=True,
            )

        await interaction.response.defer()
        try:
            await member.timeout(None, reason=f"Timeout removed by {interaction.user} ({interaction.user.id})")
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=_err("Discord відхилив дію. Перевір рольову ієрархію та права бота."),
                ephemeral=True,
            )
        except discord.HTTPException:
            return await interaction.followup.send(
                embed=_err("Discord не зміг зняти тайм-аут. Спробуй ще раз трохи пізніше."),
                ephemeral=True,
            )

        await interaction.followup.send(embed=_ok(f"{E_CHECK} З {member.mention} знято тайм-аут."))

    @app_commands.command(name="kick", description="Вигнати користувача")
    @app_commands.describe(member="Кого вигнати", reason="Причина")
    @app_commands.default_permissions(administrator=True)
    async def kick_cmd(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Не вказано"):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        target_error = _manual_target_error(interaction, member, "kick")
        if target_error:
            return await interaction.response.send_message(embed=_err(target_error), ephemeral=True)

        await interaction.response.defer()
        try:
            case_id = await apply_case(
                bot=self.bot,
                guild=interaction.guild,
                user=member,
                moderator=interaction.user,
                action="kick",
                reason=reason,
                source="manual",
                origin_text=_build_origin_text(interaction, "kick"),
            )
        except ModerationActionError as exc:
            return await interaction.followup.send(embed=_err(exc.user_message), ephemeral=True)

        await interaction.followup.send(embed=_ok(f"{E_KICK} {member.mention} вигнаний. ID `#{case_id}`."))

    @app_commands.command(name="ban", description="Забанити користувача")
    @app_commands.describe(member="Кого забанити", reason="Причина")
    @app_commands.default_permissions(administrator=True)
    async def ban_cmd(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Не вказано"):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        target_error = _manual_target_error(interaction, member, "ban")
        if target_error:
            return await interaction.response.send_message(embed=_err(target_error), ephemeral=True)

        await interaction.response.defer()
        try:
            case_id = await apply_case(
                bot=self.bot,
                guild=interaction.guild,
                user=member,
                moderator=interaction.user,
                action="ban",
                reason=reason,
                source="manual",
                origin_text=_build_origin_text(interaction, "ban"),
            )
        except ModerationActionError as exc:
            return await interaction.followup.send(embed=_err(exc.user_message), ephemeral=True)

        await interaction.followup.send(embed=_ok(f"{E_BAN} {member.mention} забанений. ID `#{case_id}`."))


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
