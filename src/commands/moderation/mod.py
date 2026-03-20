"""
mod.py
Єдиний файл для команд модерації: warn, purge, kick, ban, mute, unmute.
Команди взаємодіють з сервісом moderation.py для реєстрації у БД (Cases),
яка буде відображатися на майбутній Web-панелі.
"""
import discord
from discord import app_commands
from discord.ext import commands
import datetime
import json
from pathlib import Path
from services.moderation import apply_case

EMBED_COLOR = 0x1a1a2e
_CONFIG_PATH = Path(__file__).parents[3] / "config.json"

def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
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
    return discord.Embed(description=f"<:cutiex:1480246146076119132> {description}", color=0x2b2d31)

UNIT_MAP = {"s": 1, "m": 60, "h": 3600, "d": 86400}
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

class CustomPurgeModal(discord.ui.Modal, title="Свій термін видалення"):
    period = discord.ui.TextInput(
        label="Термін",
        placeholder="Наприклад: 10m, 2h, 3d, 30s",
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        seconds = _parse_duration(self.period.value)
        if not seconds or seconds <= 0:
            await interaction.response.send_message(embed=_err("Невірний формат. Приклади: `10m`, `2h`, `3d`"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        cutoff = discord.utils.utcnow() - datetime.timedelta(seconds=seconds)
        try:
            deleted = await interaction.channel.purge(after=cutoff)
            await interaction.followup.send(embed=_ok(f"<:trash:1477722148071145634> Видалено **{len(deleted)}** повідомлень."), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(embed=_err("Немає прав на видалення."), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=_err(f"Помилка: {e}"), ephemeral=True)


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="warn", description="Видати попередження (варн)")
    @app_commands.describe(користувач="Кого попередити", причина="Причина варну")
    @app_commands.default_permissions(administrator=True)
    async def warn_cmd(self, interaction: discord.Interaction, користувач: discord.Member, причина: str):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)
        if користувач.bot:
            return await interaction.response.send_message(embed=_err("Неможливо видати варн боту."), ephemeral=True)

        await interaction.response.defer()
        
        # Створюємо кейс через наш сервіс (який зареєструє варн у БД для сайту)
        case_id = await apply_case(
            bot=self.bot,
            guild=interaction.guild,
            user=користувач,
            moderator=interaction.user,
            action="warn",
            reason=причина
        )
        
        await interaction.followup.send(embed=_ok(f"🛡️ {користувач.mention} отримав попередження. ID `#{case_id}`."))

    @app_commands.command(name="purge", description="Очистити чат")
    @app_commands.describe(період="За який час видалити")
    @app_commands.choices(період=[
        app_commands.Choice(name="Всі повідомлення",    value="all"),
        app_commands.Choice(name="Останні 24 години",  value="1d"),
        app_commands.Choice(name="Останні 3 дні",      value="3d"),
        app_commands.Choice(name="Останній тиждень",    value="7d"),
        app_commands.Choice(name="⌨️ Свій час (5m, 2h, 1d...)", value="custom"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def purge_cmd(self, interaction: discord.Interaction, період: app_commands.Choice[str]):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        if період.value == "custom":
            return await interaction.response.send_modal(CustomPurgeModal())

        await interaction.response.defer(ephemeral=True)
        try:
            if період.value == "all":
                deleted = await interaction.channel.purge()
            else:
                days = {"1d": 1, "3d": 3, "7d": 7}.get(період.value)
                cutoff = discord.utils.utcnow() - datetime.timedelta(days=days)
                deleted = await interaction.channel.purge(after=cutoff)
            await interaction.followup.send(embed=_ok(f"<:trash:1477722148071145634> Видалено **{len(deleted)}** повідомлень."), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=_err(f"Помилка: {e}"), ephemeral=True)

    @app_commands.command(name="mute", description="Тимчасово заглушити користувача (Timeout)")
    @app_commands.describe(користувач="Кого заглушити", час="Тривалість: 10m, 1h, 1d", причина="Причина")
    @app_commands.default_permissions(administrator=True)
    async def mute_cmd(self, interaction: discord.Interaction, користувач: discord.Member, час: str, причина: str = "Не вказана"):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)
        
        seconds = _parse_duration(час)
        if not seconds or seconds <= 0:
            return await interaction.response.send_message(embed=_err("Невірний формат. Приклад: `10m`, `1h`."), ephemeral=True)

        await interaction.response.defer()
        duration_hours = max(1, seconds // 3600)

        case_id = await apply_case(
            bot=self.bot,
            guild=interaction.guild,
            user=користувач,
            moderator=interaction.user,
            action="mute",
            reason=причина,
            duration_hours=duration_hours
        )
        await interaction.followup.send(embed=_ok(f"🔇 {користувач.mention} отримав тайм-аут на **{час}**. ID `#{case_id}`."))

    @app_commands.command(name="unmute", description="Зняти тайм-аут з користувача")
    @app_commands.describe(користувач="З кого зняти заглушення")
    @app_commands.default_permissions(administrator=True)
    async def unmute_cmd(self, interaction: discord.Interaction, користувач: discord.Member):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)
        await interaction.response.defer()
        try:
            await користувач.timeout(None)
            await interaction.followup.send(embed=_ok(f"🔊 З {користувач.mention} знято тайм-аут."))
        except Exception:
            await interaction.followup.send(embed=_err("Немає прав."), ephemeral=True)

    @app_commands.command(name="kick", description="Вигнати користувача")
    @app_commands.describe(користувач="Кого вигнати", причина="Причина")
    @app_commands.default_permissions(administrator=True)
    async def kick_cmd(self, interaction: discord.Interaction, користувач: discord.Member, причина: str = "Не вказана"):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)
        await interaction.response.defer()
        
        case_id = await apply_case(
            bot=self.bot,
            guild=interaction.guild,
            user=користувач,
            moderator=interaction.user,
            action="kick",
            reason=причина
        )
        await interaction.followup.send(embed=_ok(f"🦵 {користувач.mention} вигнаний. ID `#{case_id}`."))

    @app_commands.command(name="ban", description="Забанити користувача")
    @app_commands.describe(користувач="Кого забанити", причина="Причина")
    @app_commands.default_permissions(administrator=True)
    async def ban_cmd(self, interaction: discord.Interaction, користувач: discord.Member, причина: str = "Не вказана"):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)
        await interaction.response.defer()

        case_id = await apply_case(
            bot=self.bot,
            guild=interaction.guild,
            user=користувач,
            moderator=interaction.user,
            action="ban",
            reason=причина
        )
        await interaction.followup.send(embed=_ok(f"🔨 {користувач.mention} забанений. ID `#{case_id}`."))

    @app_commands.command(name="warns", description="Переглянути історію попереджень користувача")
    @app_commands.describe(користувач="Чию історію переглянути")
    @app_commands.default_permissions(administrator=True)
    async def warns_cmd(self, interaction: discord.Interaction, користувач: discord.Member):
        if not check_permissions(interaction):
            return await interaction.response.send_message(embed=_err("Недостатньо прав."), ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        from modules.db import get_database
        _db = get_database()

        # Get decay settings
        settings = await _db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        decay_days = settings.get("warn_decay_days", 0)

        query = {
            "guild_id": interaction.guild.id,
            "user_id": користувач.id,
            "action": "warn"
        }

        cursor = _db.cases.find(query).sort("timestamp", -1).limit(20)
        warns = await cursor.to_list(length=20)

        embed = discord.Embed(
            title=f"<:warn:1477376152191373504> Історія попереджень",
            description=f"Користувач: {користувач.mention}",
            color=EMBED_COLOR,
        )

        if not warns:
            embed.add_field(name="Результат", value="<:krestik:1476693091355463842> Попереджень не знайдено.", inline=False)
        else:
            active_count = 0
            for i, w in enumerate(warns, 1):
                ts = w.get("timestamp")
                ts_str = discord.utils.format_dt(ts, "R") if ts else "невідомо"
                mod_id = w.get("moderator_id")
                reason = w.get("reason", "Не вказано")
                case_id = w.get("case_id", "???")

                # Check if expired by decay
                expired = False
                if decay_days > 0 and ts:
                    from datetime import datetime, timezone, timedelta
                    cutoff = datetime.now(timezone.utc) - timedelta(days=decay_days)
                    if ts < cutoff:
                        expired = True

                if not expired:
                    active_count += 1

                status = "~~`Спав`~~" if expired else ""
                mod_text = f"<@{mod_id}>" if mod_id else "Система"

                embed.add_field(
                    name=f"#{case_id} — {ts_str} {status}",
                    value=f"**Причина:** {reason}\n**Модератор:** {mod_text}",
                    inline=False,
                )

            embed.set_footer(text=f"Активних варнів: {active_count} / {len(warns)} загалом")

        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
