import discord
from discord import app_commands
from discord.ext import commands
import time
import random
import string
from io import BytesIO

try:
    from captcha.image import ImageCaptcha
except ImportError:
    ImageCaptcha = None

from modules.db import get_database
from repositories.user import get_user
from commands.economy.quests import quest_hook
from utils.eco_helpers import apply_inflation
from utils.ui_contract import gameplay_result_embed, set_surface_footer, surface_embed

db = get_database()

class CaptchaModal(discord.ui.Modal, title="🤖 Перевірка на людяність"):
    captcha_input = discord.ui.TextInput(
        label="Введіть текст з картинки:",
        placeholder="Літери і цифри з малюнку",
        min_length=4,
        max_length=6
    )

    def __init__(self, expected_text: str, daily_callback):
        super().__init__()
        self.expected_text = expected_text
        self.daily_callback = daily_callback

    async def on_submit(self, interaction: discord.Interaction):
        if self.captcha_input.value.strip() == self.expected_text:
            await interaction.response.edit_message(content="<:check:1485597845883981905> Капча пройдена успішно!", embed=None, view=None, attachments=[])
            await self.daily_callback(interaction)
        else:
            await interaction.response.edit_message(content="<:close:1485598320935174317> Неправильний текст. Спробуй ще раз пізніше.", embed=None, view=None, attachments=[])

class CaptchaView(discord.ui.View):
    def __init__(self, owner_id: int, expected_text: str, daily_callback):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.expected_text = expected_text
        self.daily_callback = daily_callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("<:close:1485598320935174317> Це не твоя капча!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Відповісти", style=discord.ButtonStyle.primary, emoji="🤖")
    async def enter_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CaptchaModal(self.expected_text, self.daily_callback))

class DailyCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def execute_daily(self, interaction: discord.Interaction, eco: dict, user_data: dict, now: int, last_daily: int):
        cd_hours = eco.get("daily_cooldown", 24)
        cooldown = int(cd_hours * 3600)
        streak = user_data.get("daily_streak", 0)
        
        if last_daily and (now - last_daily) > (cooldown * 2):
            streak = 0
            
        streak += 1

        STREAK_BONUS_CAP = 30  
        base_amount  = eco.get("daily_amount", 200)
        streak_bonus = eco.get("daily_streak_bonus", 50) * (min(streak, STREAK_BONUS_CAP) - 1)
        earned       = base_amount + streak_bonus
        # Податок на багатство для хай-левелів
        from utils.eco_helpers import calculate_tax
        wallet = user_data.get("wallet", 0)
        bank = user_data.get("bank", 0)
        final_earned, tax, tax_pct_str = calculate_tax(earned, wallet, bank)

        log_item = {"log": f"🟢 **{final_earned}** | Щоденна нагорода (Streak: {streak}) | <t:{now}:t>"}

        await db.users.update_one(
            {"guild_id": interaction.guild.id, "user_id": interaction.user.id},
            {
                "$inc": {"wallet": final_earned, "total_earned": final_earned},
                "$set": {"daily_last": now, "daily_streak": streak},
                "$push": {"eco_history": {"$each": [log_item], "$slice": -50}}
            }
        )
        from modules.db import invalidate_user_data
        await invalidate_user_data(interaction.guild.id, interaction.user.id)
        
        await quest_hook(interaction.guild.id, interaction.user.id, "economy.daily")
        await apply_inflation(db, interaction.guild.id, final_earned, eco)

        emoji = eco.get("currency_emoji", "<:coin:1485610808003133552>")
        flame = "<:flame:1485618663489929356>"
        calendar = "<:info:1485638054201921536>"
        
        earned_text = f"{final_earned} {emoji}"
        if tax > 0:
            earned_text += f"\n*(Податок на багатство {tax_pct_str}: -{tax} {emoji})*"

        embed = gameplay_result_embed(
            f"{calendar} Щоденна нагорода",
            f"Ти успішно отримав свою щоденну нагороду!\n\n**Базова нагорода:** {base_amount} {emoji}\n**Бонус ({streak} {flame}):** +{streak_bonus} {emoji}\n\n**Всього зараховано:** {earned_text}",
            tone="success",
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="daily", description="Отримати щоденну нагороду")
    async def daily(self, interaction: discord.Interaction):
        try:
            from modules.db import get_guild_settings
            settings = await get_guild_settings(db, interaction.guild.id)
            eco = settings.get("economy", {})
            if not eco.get("enabled", True):
                await interaction.response.send_message("<:close:1485598320935174317> Економіка на цьому сервері вимкнена.", ephemeral=True)
                return
            # Ріжемо фермерів: твінкам тут не місце
            from utils.eco_helpers import check_account_age
            if not await check_account_age(interaction, eco):
                return

            user_data = await get_user(db, interaction.guild.id, interaction.user.id)
            now = int(time.time())
            last_daily = user_data.get("daily_last", 0)
            
            cd_hours = eco.get("daily_cooldown", 24)
            cooldown = int(cd_hours * 3600)

            if last_daily and (now - last_daily) < cooldown:
                remaining = int(cooldown - (now - last_daily))
                h, m = divmod(remaining // 60, 60)
                time_str = f"{h}г {m}хв"
                await interaction.response.send_message(f"<:hourglass:1485598603937579181> Ти вже отримав свою щоденну нагороду! Повертайся через **{time_str}**.", ephemeral=True)
                return

            if eco.get("captcha_enabled", False) and ImageCaptcha:
                chars = string.ascii_uppercase + string.digits
                captcha_text = ''.join(random.choices(chars, k=5))
                
                image = ImageCaptcha(width=280, height=90, font_sizes=(42, 50, 56))
                data = image.generate(captcha_text)
                image_bytes = data.read()
                
                file = discord.File(fp=BytesIO(image_bytes), filename="captcha.png")
                embed = surface_embed(
                    "gameplay",
                    "🤖 Перевірка",
                    "Розвʼяжи капчу щоб отримати щоденну нагороду.\nНатисни **Відповісти** коли будеш готовий.",
                    tone="warning",
                )
                embed.set_image(url="attachment://captcha.png")
                set_surface_footer(embed, "gameplay", "Captcha потрібна лише для захисту від фарму.")
                
                async def daily_callback(inter):
                    await self.execute_daily(inter, eco, user_data, now, last_daily)
                    
                view = CaptchaView(interaction.user.id, captcha_text, daily_callback)
                
                await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
            else:
                await self.execute_daily(interaction, eco, user_data, now, last_daily)

        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"<:warning:1485598476850040843> Помилка: `{e}`", ephemeral=True)
            else:
                await interaction.followup.send(f"<:warning:1485598476850040843> Помилка: `{e}`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(DailyCommand(bot))
