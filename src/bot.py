import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import sys
import traceback
from dotenv import load_dotenv
from config.constants import Emojis
from modules.logger import Logger
from rich.progress import Progress

log = Logger("BOT")

# --- МАГІЯ ШЛЯХІВ ---
# Отримуємо точну папку, де лежить цей файл (src/bot.py)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Піднімаємось на рівень вище, щоб знайти config.json і .env (в папку bot1)
ROOT_DIR = os.path.dirname(CURRENT_DIR)

# Завантаження конфігу
try:
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as f:
        config = json.load(f)
except FileNotFoundError:
    log.error(f"config.json not found in {ROOT_DIR}")
    exit(1)

# Завантаження змінних середовища
load_dotenv(os.path.join(ROOT_DIR, ".env"))
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    log.error("TOKEN not found in .env file")
    exit(1)

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.reactions = True
intents.voice_states = True
intents.message_content = True

from services.automod import load_automod_cache
from services.metrics import inc_global_metric, mark_user_active, set_global_timestamp
from modules.db import get_database
from utils.restrictions import normalize_command_restrictions, normalize_role_ids

db = get_database()


# ── Command Tree з перевіркою обмежень ────────────────────────────────────────
# Кеш: { guild_id: { "meme": [ch_ids], "avatar": [ch_ids], ... } }
_restriction_cache: dict[int, dict] = {}
_SYNC_MANAGER_IDS = {961262391314755665}


async def _normalize_guild_restrictions_doc(doc: dict) -> dict[str, object]:
    restrictions = normalize_command_restrictions(doc.get("command_restrictions"))
    bypass_role_ids = normalize_role_ids(doc.get("command_bypass_role_ids"))

    updates = {}
    if restrictions != doc.get("command_restrictions", {}):
        updates["command_restrictions"] = restrictions
    if bypass_role_ids != doc.get("command_bypass_role_ids", []):
        updates["command_bypass_role_ids"] = bypass_role_ids
    if updates:
        await db.guild_settings.update_one({"_id": doc["_id"]}, {"$set": updates})

    return {
        "command_restrictions": restrictions,
        "command_bypass_role_ids": bypass_role_ids,
    }


class RestrictedTree(app_commands.CommandTree):
    """CommandTree з вбудованою перевіркою обмежень команд по каналах."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return True

        guild_id = interaction.guild.id
        restriction_payload = _restriction_cache.get(guild_id)

        # Fallback: якщо кеш порожній, підвантажуємо з БД.
        if restriction_payload is None:
            doc = await db.guild_settings.find_one({"_id": guild_id})
            if doc and ("command_restrictions" in doc or "command_bypass_role_ids" in doc):
                restriction_payload = await _normalize_guild_restrictions_doc(doc)
                _restriction_cache[guild_id] = restriction_payload
                log.info(f"[RESTRICT] Loaded from DB for guild {guild_id}: {restriction_payload}")
            else:
                _restriction_cache[guild_id] = {}
                return True

        restrictions = restriction_payload.get("command_restrictions", {}) if restriction_payload else {}
        bypass_role_ids = set(restriction_payload.get("command_bypass_role_ids", [])) if restriction_payload else set()

        if not restrictions:
            return True

        command = interaction.command
        if not command:
            return True

        cmd_name = command.name
        if cmd_name not in restrictions:
            return True

        allowed_channels = restrictions[cmd_name]
        if not allowed_channels:
            await inc_global_metric("commands_used_total")
            await mark_user_active(interaction.guild.id, interaction.user.id)
            return True

        if interaction.channel_id in allowed_channels:
            await inc_global_metric("commands_used_total")
            await mark_user_active(interaction.guild.id, interaction.user.id)
            return True

        if interaction.guild.owner_id == interaction.user.id:
            await inc_global_metric("commands_used_total")
            await mark_user_active(interaction.guild.id, interaction.user.id)
            return True

        member_roles = getattr(interaction.user, "roles", [])
        if bypass_role_ids and any(getattr(role, "id", 0) in bypass_role_ids for role in member_roles):
            await inc_global_metric("commands_used_total")
            await mark_user_active(interaction.guild.id, interaction.user.id)
            return True

        ch_list = ", ".join(f"<#{c}>" for c in allowed_channels)
        log.info(f"[RESTRICT] BLOCKED: /{cmd_name} in ch={interaction.channel_id}, allowed={allowed_channels}")
        await interaction.response.send_message(
            f"{Emojis.CROSS.value} Команду `/{cmd_name}` можна використовувати лише в: {ch_list}",
            ephemeral=True,
        )
        return False

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await inc_global_metric("command_errors_total")
        original = getattr(error, "original", error)
        command_name = getattr(interaction.command, "name", "unknown")
        guild_id = getattr(interaction.guild, "id", "dm")
        user_id = getattr(interaction.user, "id", "unknown")
        log.error(f"[APP] /{command_name} failed for user={user_id} guild={guild_id}: {original}")
        log.error("".join(traceback.format_exception(type(original), original, original.__traceback__)).strip())

        if isinstance(error, app_commands.CommandOnCooldown):
            message = f"{Emojis.HOURGLASS.value} Зачекай **{error.retry_after:.1f} с** і спробуй ще раз."
        elif isinstance(error, app_commands.MissingPermissions):
            message = f"{Emojis.CROSS.value} У тебе недостатньо прав для цієї команди."
        elif isinstance(error, app_commands.BotMissingPermissions):
            message = f"{Emojis.CROSS.value} Мені не вистачає прав для виконання цієї команди."
        elif isinstance(error, app_commands.CheckFailure):
            message = f"{Emojis.CROSS.value} Ця команда зараз недоступна."
        else:
            message = (
                f"{Emojis.WARN.value} Щось зламалось під час виконання команди. "
                "Спробуй ще раз трохи пізніше."
            )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass


class HeroesBot(commands.Bot):
    """Підклас Bot з переозначеним setup_hook (правильний API discord.py)."""

    async def setup_hook(self):
        success = 0
        errors = 0
        extensions = []

        log.info(f"Scanning for extensions in: {CURRENT_DIR}")
        await load_automod_cache(self)

        # 1. Івенти (src/events)
        events_path = os.path.join(CURRENT_DIR, "events")
        if os.path.exists(events_path):
            for filename in os.listdir(events_path):
                if filename.endswith(".py") and not filename.startswith("_"):
                    # Якщо `python src/bot.py`, sys.path може не включати `src`
                    extensions.append(("event", f"events.{filename[:-3]}", filename[:-3]))
        else:
            log.warning(f"Events folder not found at: {events_path}")

        # 2. Команди (src/commands/**)
        commands_path = os.path.join(CURRENT_DIR, "commands")
        if os.path.exists(commands_path):
            for category in os.listdir(commands_path):
                category_path = os.path.join(commands_path, category)
                if os.path.isdir(category_path):
                    for filename in os.listdir(category_path):
                        if (
                            filename.endswith(".py")
                            and not filename.startswith("_")
                            and not filename.endswith(("_shared.py", "_extras.py"))
                        ):
                            extensions.append(
                                (
                                    "command",
                                    f"commands.{category}.{filename[:-3]}",
                                    f"{category}.{filename[:-3]}",
                                )
                            )
        else:
            log.warning(f"Commands folder not found at: {commands_path}")

        # 3. Сервіси
        extensions.append(("service", "services.scheduler", "scheduler"))

        # Завантаження з прогрес-баром
        with Progress() as progress:
            task = progress.add_task("[green]Loading extensions...", total=len(extensions))
            for ext_type, ext_path, ext_name in extensions:
                try:
                    await self.load_extension(ext_path)
                    log.info(f"Loaded {ext_type}: {ext_name}")
                    success += 1
                except Exception as exc:
                    log.error(f"Failed to load {ext_type} {ext_name}: {exc}")
                    errors += 1
                progress.update(task, advance=1)

        log.info(f"Extensions loaded: {success} success, {errors} errors")
        if errors > 0:
            log.critical(f"{errors} cog(s) not loaded — частина функцій бота недоступна! Перевір логи вище.")

        # Automatic sync на старті вимкнений. Використовуємо ручний !sync.
        log.info("Automatic slash sync disabled on startup. Use !sync manually when command schema changes.")


bot = HeroesBot(
    command_prefix=config.get("prefix", "!"),
    intents=intents,
    tree_cls=RestrictedTree,
)


# ── Хуки для перезавантаження кешу обмежень ───────────────────────────────────
async def _load_restrictions():
    """Завантажити обмеження при старті."""
    _restriction_cache.clear()
    async for doc in db.guild_settings.find(
        {
            "$or": [
                {"command_restrictions": {"$exists": True}},
                {"command_bypass_role_ids": {"$exists": True}},
            ]
        }
    ):
        _restriction_cache[doc["_id"]] = await _normalize_guild_restrictions_doc(doc)
    log.info(f"[RESTRICT] Loaded restrictions for {len(_restriction_cache)} guild(s)")


async def reload_restrictions_cache(guild_id: int):
    doc = await db.guild_settings.find_one({"_id": guild_id})
    if doc and ("command_restrictions" in doc or "command_bypass_role_ids" in doc):
        _restriction_cache[guild_id] = await _normalize_guild_restrictions_doc(doc)
    else:
        _restriction_cache.pop(guild_id, None)


def _is_sync_manager(user_id: int) -> bool:
    return user_id in _SYNC_MANAGER_IDS


# Зберігаємо функцію в bot для доступу з інших модулів
bot.reload_restrictions = reload_restrictions_cache


@bot.event
async def on_ready():
    await _load_restrictions()
    from services.auction_manager import setup_auction_manager

    await setup_auction_manager(bot).initialize()
    log.info(f"Bot {bot.user} is ready! Loaded {len(bot.cogs)} cogs")


@bot.command(name="sync", hidden=True)
async def sync_commands(ctx: commands.Context, scope: str = "guild"):
    if not _is_sync_manager(ctx.author.id):
        return

    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

    async def _send_sync_result(message: str):
        try:
            await ctx.author.send(message)
        except discord.HTTPException:
            try:
                await ctx.send(message, delete_after=10)
            except discord.HTTPException:
                pass

    normalized = scope.strip().lower()
    if normalized in {"global", "g"}:
        synced = await bot.tree.sync()
        await set_global_timestamp("last_command_sync_at")
        await _send_sync_result(f"{Emojis.CHECK.value} Global sync done. Synced **{len(synced)}** command(s).")
        log.info(f"[SYNC] Global sync requested by {ctx.author} ({ctx.author.id}) -> {len(synced)} command(s)")
        return

    guild_id = 0
    scope_label = "guild"
    if normalized in {"guild", "here", "current", "c"}:
        guild_id = getattr(ctx.guild, "id", 0) or 0
    elif normalized in {"dev", "config"}:
        guild_id = int(config.get("guild", 0) or 0)
        scope_label = "dev guild"
    elif normalized.isdigit():
        guild_id = int(normalized)
        scope_label = "explicit guild"
    else:
        guild_id = getattr(ctx.guild, "id", 0) or int(config.get("guild", 0) or 0)

    if guild_id <= 0:
        await _send_sync_result(f"{Emojis.CROSS.value} Немає guild ID для sync. Запусти `!sync` у сервері, `!sync dev` або `!sync global`.")
        return

    guild_obj = discord.Object(id=guild_id)
    bot.tree.clear_commands(guild=guild_obj)
    bot.tree.copy_global_to(guild=guild_obj)
    synced = await bot.tree.sync(guild=guild_obj)
    await set_global_timestamp("last_command_sync_at")
    await _send_sync_result(
        f"{Emojis.CHECK.value} {scope_label.capitalize()} sync done for `{guild_id}`. Synced **{len(synced)}** command(s)."
    )
    log.info(
        f"[SYNC] {scope_label} sync requested by {ctx.author} ({ctx.author.id}) for guild={guild_id} -> {len(synced)} command(s)"
    )


bot.run(TOKEN)

