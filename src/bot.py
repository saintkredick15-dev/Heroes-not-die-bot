import discord
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

bot = commands.Bot(command_prefix=config.get("prefix", "!"), intents=intents)

@bot.event
async def on_ready():
    log.info(f"Bot {bot.user} is ready! Loaded {len(bot.cogs)} cogs")

@bot.event
async def setup_hook():
    success = 0
    errors = 0
    extensions = []
    
    log.info(f"Scanning for extensions in: {CURRENT_DIR}")

    # 1. Шукаємо івенти (src/events)
    events_path = os.path.join(CURRENT_DIR, 'events')
    if os.path.exists(events_path):
        for filename in os.listdir(events_path):
            if filename.endswith('.py') and not filename.startswith('_'):
                extensions.append(('event', f'src.events.{filename[:-3]}', filename[:-3]))
    else:
        log.warning(f"Events folder not found at: {events_path}")
    
    # 2. Шукаємо команди (src/commands)
    commands_path = os.path.join(CURRENT_DIR, 'commands')
    if os.path.exists(commands_path):
        for category in os.listdir(commands_path):
            category_path = os.path.join(commands_path, category)
            if os.path.isdir(category_path):
                for filename in os.listdir(category_path):
                    if filename.endswith('.py') and not filename.startswith('_'):
                        extensions.append(('command', f'src.commands.{category}.{filename[:-3]}', f'{category}.{filename[:-3]}'))
    else:
        log.warning(f"Commands folder not found at: {commands_path}")
    
    # Завантаження
    with Progress() as progress:
        task = progress.add_task("[green]Loading extensions...", total=len(extensions))
        
        for ext_type, ext_path, ext_name in extensions:
            try:
                await bot.load_extension(ext_path)
                log.info(f"Loaded {ext_type}: {ext_name}")
                success += 1
            except Exception as e:
                log.error(f"Failed to load {ext_type} {ext_name}: {e}")
                errors += 1
            progress.update(task, advance=1)
    
    log.info(f"Extensions loaded: {success} success, {errors} errors")
    
    await bot.tree.sync()
    log.info("Synced slash commands globally")

bot.run(TOKEN)