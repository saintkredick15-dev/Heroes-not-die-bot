import discord
from discord import app_commands
from discord.ext import commands
import json
import datetime
from pathlib import Path
from modules.db import get_database
from repositories.user import get_user, update_user_raw

db = get_database()

_CONFIG_PATH = Path(__file__).parents[3] / "config.json"

# ── Кастомні емодзі ──────────────────────────────────────────────────────────
E_BAN    = "<:ban:1476199074494681170>"
E_KICK   = "<:kick:1476199862344351785>"
E_MUTE   = "<:mutemicro:1476200127063396443>"
E_STAR   = "<:star:1475954213455532067>"

EMBED_COLOR = 0x1a1a2e

UNIT_MAP = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_duration(text: str) -> int | None:
    """Parse e.g. '5m', '2h', '1d' into seconds. Returns None on error."""
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
                embed=discord.Embed(
                    description="❌ Невірний формат. Приклади: `10m`, `2h`, `3d`",
                    color=0x2b2d31,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        cutoff = discord.utils.utcnow() - datetime.timedelta(seconds=seconds)
        try:
            deleted = await interaction.channel.purge(after=cutoff)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"🗑️ Видалено **{len(deleted)}** повідомлень (за {self.period.value}).",
                    color=EMBED_COLOR,
                ),
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(description="❌ Немає прав на видалення.", color=0x2b2d31), ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=discord.Embed(description=f"❌ Помилка: {e}", color=0x2b2d31), ephemeral=True
            )


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[admin] Помилка завантаження config.json: {e}")
        return {}


def check_permissions(interaction: discord.Interaction) -> bool:
    config = _load_config()
    return (
        interaction.user.guild_permissions.administrator
        or interaction.user.id in config.get("dev", [])
    )


def _ok(description: str) -> discord.Embed:
    return discord.Embed(description=description, color=EMBED_COLOR)


def _err(description: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {description}", color=0x2b2d31)


class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="xp", description="Управління XP користувачів")
    @app_commands.describe(дія="Що зробити з XP", користувач="Цільовий користувач", кількість="XP або рівень")
    @app_commands.choices(дія=[
        app_commands.Choice(name="Додати XP",          value="add"),
        app_commands.Choice(name="Забрати XP",         value="remove"),
        app_commands.Choice(name="Встановити рівень",  value="setlevel"),
        app_commands.Choice(name="Скинути XP",         value="reset"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def xp_manage(
        self,
        interaction: discord.Interaction,
        дія: app_commands.Choice[str],
        користувач: discord.Member,
        кількість: int = 0,
    ):
        if not check_permissions(interaction):
            await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)
            return

        data = await get_user(db, interaction.guild.id, користувач.id)

        if дія.value == "add":
            if кількість <= 0:
                await interaction.response.send_message(embed=_err("XP має бути > 0."), ephemeral=True)
                return
            await update_user_raw(db, interaction.guild.id, користувач.id, {"xp": data["xp"] + кількість})
            await interaction.response.send_message(
                embed=_ok(f"{E_STAR} **{кількість} XP** додано {користувач.mention}."), ephemeral=True
            )

        elif дія.value == "remove":
            if кількість <= 0:
                await interaction.response.send_message(embed=_err("XP має бути > 0."), ephemeral=True)
                return
            await update_user_raw(db, interaction.guild.id, користувач.id, {"xp": max(data["xp"] - кількість, 0)})
            await interaction.response.send_message(
                embed=_ok(f"🗑️ **{кількість} XP** забрано у {користувач.mention}."), ephemeral=True
            )

        elif дія.value == "setlevel":
            if кількість <= 0:
                await interaction.response.send_message(embed=_err("Рівень має бути > 0."), ephemeral=True)
                return
            await update_user_raw(db, interaction.guild.id, користувач.id, {"level": кількість})
            await interaction.response.send_message(
                embed=_ok(f"🔧 Рівень {користувач.mention} → **{кількість}**."), ephemeral=True
            )

        elif дія.value == "reset":
            await update_user_raw(db, interaction.guild.id, користувач.id, {"xp": 0})
            await interaction.response.send_message(
                embed=_ok(f"🔄 XP {користувач.mention} скинуто до **0**."), ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))