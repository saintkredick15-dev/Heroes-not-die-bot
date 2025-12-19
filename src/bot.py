import discord
from discord.ext import commands
import json
import os
from dotenv import load_dotenv
from modules.logger import Logger
from rich.progress import Progress

log = Logger("BOT")

# Load configuration
try:
    with open("../config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
except FileNotFoundError:
    log.error("config.json file not found")
    exit(1)
except json.JSONDecodeError:
    log.error("Invalid JSON in config.json")
    exit(1)

# Load environment variables
load_dotenv("../.env")
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    log.error("TOKEN not found in .env file")
    exit(1)

# Configure bot intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.reactions = True
intents.voice_states = True
intents.message_content = True

# Initialize bot
bot = commands.Bot(command_prefix=config.get("prefix", "!"), intents=intents)

@bot.event
async def on_ready():
    log.info(f"Bot {bot.user} is ready! Loaded {len(bot.cogs)} cogs")

@bot.event
async def setup_hook():
    success = 0
    errors = 0
    extensions = []
    
    # Collect all extensions
    if os.path.exists('./events'):
        for filename in os.listdir('./events'):
            if filename.endswith('.py') and not filename.startswith('_'):
                extensions.append(('event', f'events.{filename[:-3]}', filename[:-3]))
    
    if os.path.exists('./commands'):
        for category in os.listdir('./commands'):
            if os.path.isdir(f'./commands/{category}'):
                for filename in os.listdir(f'./commands/{category}'):
                    # ВИПРАВЛЕННЯ: Ігноруємо файли, що починаються з '_'
                    if filename.endswith('.py') and not filename.startswith('_'):
                        extensions.append(('command', f'commands.{category}.{filename[:-3]}', f'{category}.{filename[:-3]}'))
    
    # Load with progress bar
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
    
    # Sync slash commands globally
    await bot.tree.sync()
    log.info("Synced slash commands globally")

bot.run(TOKEN)