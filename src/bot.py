import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import sys
from dotenv import load_dotenv
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
from modules.db import get_database
db = get_database()


# ── Command Tree з перевіркою обмежень ────────────────────────────────────────
# Кеш: { guild_id: { "meme": [ch_ids], "avatar": [ch_ids], ... } }
_restriction_cache: dict[int, dict] = {}


class RestrictedTree(app_commands.CommandTree):
    """CommandTree з вбудованою перевіркою обмежень команд по каналах."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return True

        guild_id = interaction.guild.id
        restrictions = _restriction_cache.get(guild_id)

        # Fallback: якщо кеш порожній — підвантажуємо з БД
        if restrictions is None:
            doc = await db.guild_settings.find_one({"_id": guild_id})
            if doc and "command_restrictions" in doc:
                restrictions = doc["command_restrictions"]
                _restriction_cache[guild_id] = restrictions
                log.info(f"[RESTRICT] Loaded from DB for guild {guild_id}: {restrictions}")
            else:
                _restriction_cache[guild_id] = {}
                return True

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
            return True

        if interaction.channel_id in allowed_channels:
            return True

        ch_list = ", ".join(f"<#{c}>" for c in allowed_channels)
        log.info(f"[RESTRICT] BLOCKED: /{cmd_name} in ch={interaction.channel_id}, allowed={allowed_channels}")
        await interaction.response.send_message(
            f"❌ Команду `/{cmd_name}` можна використовувати лише в: {ch_list}",
            ephemeral=True,
        )
        return False


class HeroesBot(commands.Bot):
    """Підклас Bot з переозначеним setup_hook (правильний API discord.py)."""

    async def setup_hook(self):
        success = 0
        errors = 0
        extensions = []

        log.info(f"Scanning for extensions in: {CURRENT_DIR}")
        await load_automod_cache(self)

        # 1. Івенти (src/events)
        events_path = os.path.join(CURRENT_DIR, 'events')
        if os.path.exists(events_path):
            for filename in os.listdir(events_path):
                if filename.endswith('.py') and not filename.startswith('_'):
                    # Якщо `python src/bot.py`, sys.path може не включати `src`
                    extensions.append(('event', f'events.{filename[:-3]}', filename[:-3]))
        else:
            log.warning(f"Events folder not found at: {events_path}")

        # 2. Команди (src/commands/**)
        commands_path = os.path.join(CURRENT_DIR, 'commands')
        if os.path.exists(commands_path):
            for category in os.listdir(commands_path):
                category_path = os.path.join(commands_path, category)
                if os.path.isdir(category_path):
                    for filename in os.listdir(category_path):
                        if filename.endswith('.py') and not filename.startswith('_'):
                            extensions.append((
                                'command',
                                f'commands.{category}.{filename[:-3]}',
                                f'{category}.{filename[:-3]}',
                            ))
        else:
            log.warning(f"Commands folder not found at: {commands_path}")

        # Завантаження з прогрес-баром
        with Progress() as progress:
            task = progress.add_task("[green]Loading extensions...", total=len(extensions))
            for ext_type, ext_path, ext_name in extensions:
                try:
                    await self.load_extension(ext_path)
                    log.info(f"Loaded {ext_type}: {ext_name}")
                    success += 1
                except Exception as e:
                    log.error(f"Failed to load {ext_type} {ext_name}: {e}")
                    errors += 1
                progress.update(task, advance=1)

        log.info(f"Extensions loaded: {success} success, {errors} errors")
        if errors > 0:
            log.critical(
                f"{errors} cog(s) not loaded — частина функцій бота недоступна! "
                "Перевір логи вище."
            )

        # Sync slash-команд глобально (до 1 год щоб з'явились у всіх)
        # Для dev — замінити на bot.tree.sync(guild=discord.Object(id=config["guild"]))
        await self.tree.sync()
        log.info("Synced slash commands globally")


bot = HeroesBot(
    command_prefix=config.get("prefix", "!"),
    intents=intents,
    tree_cls=RestrictedTree,
)


# ── Хуки для перезавантаження кешу обмежень ───────────────────────────────────

async def _load_restrictions():
    """Завантажити обмеження при старті."""
    _restriction_cache.clear()
    async for doc in db.guild_settings.find({"command_restrictions": {"$exists": True}}):
        _restriction_cache[doc["_id"]] = doc.get("command_restrictions", {})
    log.info(f"[RESTRICT] Loaded restrictions for {len(_restriction_cache)} guild(s)")


async def reload_restrictions_cache(guild_id: int):
    doc = await db.guild_settings.find_one({"_id": guild_id})
    if doc and "command_restrictions" in doc:
        _restriction_cache[guild_id] = doc["command_restrictions"]
    else:
        _restriction_cache.pop(guild_id, None)

# Зберігаємо функцію в бот для доступу з інших модулів
bot.reload_restrictions = reload_restrictions_cache


@bot.event
async def on_ready():
    await _load_restrictions()
    log.info(f"Bot {bot.user} is ready! Loaded {len(bot.cogs)} cogs")


bot.run(TOKEN)