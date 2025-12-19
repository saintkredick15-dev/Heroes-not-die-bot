import discord
from discord.ext import commands
import json
import os
from dotenv import load_dotenv
from modules.logger import Logger
from rich.progress import Progress

log = Logger("BOT")

# Завантаження конфігу
try:
    with open("../config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
except FileNotFoundError:
    # Спробуємо знайти конфіг в поточній папці (якщо запуск з src)
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except:
        log.error("config.json file not found")
        exit(1)

# Завантаження змінних середовища
load_dotenv("../.env")
TOKEN = os.getenv("TOKEN")

# Якщо токена немає, пробуємо шукати .env в поточній папці
if not TOKEN:
    load_dotenv(".env")
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
    
    # --- ВИПРАВЛЕННЯ ШЛЯХІВ ТУТ ---
    
    # 1. Шукаємо івенти в src/events
    if os.path.exists('./src/events'):
        for filename in os.listdir('./src/events'):
            if filename.endswith('.py') and not filename.startswith('_'):
                # Важливо: додаємо 'src.' на початок
                extensions.append(('event', f'src.events.{filename[:-3]}', filename[:-3]))
    
    # 2. Шукаємо команди в src/commands
    if os.path.exists('./src/commands'):
        for category in os.listdir('./src/commands'):
            if os.path.isdir(f'./src/commands/{category}'):
                for filename in os.listdir(f'./src/commands/{category}'):
                    if filename.endswith('.py') and not filename.startswith('_'):
                        # Важливо: додаємо 'src.' на початок
                        extensions.append(('command', f'src.commands.{category}.{filename[:-3]}', f'{category}.{filename[:-3]}'))
    
    # Завантаження з прогрес-баром
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