import discord
from discord import app_commands
from discord.ext import commands

from commands.administration.economy_setup_shared import get_eco, normalize_currency_emoji
from config.constants import Emojis as _E
from modules.db import get_database
from utils.eco_helpers import make_log
from utils.ui_contract import add_section, gameplay_result_embed, set_surface_footer, surface_embed

db = get_database()

E_COIN = _E.COIN.value
E_CROSS = "<:close:1485598320935174317>"
E_BANK = "<:bank_safe:1485637217132216571>"


def generate_progress_bar(current: int, total: int, length: int = 20) -> str:
    filled_char = "\u2588"
    empty_char = "\u2591"
    if total <= 0:
        return empty_char * length
    percent = min(1.0, current / total)
    filled = int(length * percent)
    empty = length - filled
    return filled_char * filled + empty_char * empty


def build_fund_embed(eco: dict, guild: discord.Guild | None = None) -> discord.Embed:
    goal = eco.get("fund_goal", 1_000_000)
    current = eco.get("fund_current", 0)
    curr_emoji = normalize_currency_emoji(eco.get("currency_emoji", E_COIN))
    pct = (current / goal * 100) if goal > 0 else 0
    bar = generate_progress_bar(current, goal, 20)

    embed = surface_embed(
        "gameplay",
        f"{E_BANK} Фонд сервера",
        "Спільний резерв на великі серверні покращення та майбутні цілі.",
        tone="default",
    )
    add_section(
        embed,
        "Прогрес збору",
        [
            f"`{bar}` **{pct:.1f}%**",
            f"Зібрано: `{current:,}` / `{goal:,}` {curr_emoji}",
        ],
    )
    set_surface_footer(embed, "gameplay", "Внесок списується з гаманця й одразу додається у фонд.")
    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


class FundDonateModal(discord.ui.Modal, title="Зробити внесок у фонд"):
    amount = discord.ui.TextInput(label="Сума внеску", placeholder="1000", max_length=15)

    def __init__(self, eco: dict, view: "FundView"):
        super().__init__()
        self.eco = eco
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.amount.value)
            if val <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(f"{E_CROSS} Введи коректне число.", ephemeral=True)

        user_id = interaction.user.id
        guild_id = interaction.guild.id

        result = await db.users.find_one_and_update(
            {"guild_id": guild_id, "user_id": user_id, "wallet": {"$gte": val}},
            {"$inc": {"wallet": -val}, "$push": {"eco_history": {"$each": [make_log(-val, "Внесок у фонд сервера")], "$slice": -50}}},
        )
        if not result:
            return await interaction.response.send_message(f"{E_CROSS} Недостатньо коштів у гаманці для внеску.", ephemeral=True)

        await db.guild_settings.update_one(
            {"_id": guild_id},
            {"$inc": {"economy.fund_current": val}},
            upsert=True,
        )
        from modules.db import get_guild_settings, invalidate_guild_settings, invalidate_user_data

        await invalidate_user_data(guild_id, user_id)
        await invalidate_guild_settings(guild_id)

        await interaction.response.send_message(
            embed=gameplay_result_embed(
                "Внесок зараховано",
                f"Ти успішно переказав **{val:,}** {normalize_currency_emoji(self.eco.get('currency_emoji', E_COIN))} у фонд сервера.",
                tone="success",
            ),
            ephemeral=True,
        )

        settings = await get_guild_settings(db, guild_id)
        updated_eco = get_eco(settings)
        await interaction.message.edit(embed=build_fund_embed(updated_eco, interaction.guild))


class FundView(discord.ui.View):
    def __init__(self, eco: dict):
        super().__init__(timeout=None)
        self.eco = eco

    @discord.ui.button(label="Внести кошти", style=discord.ButtonStyle.success, emoji="<:coins:1485612564619727011>")
    async def donate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FundDonateModal(self.eco, self))


class FondsCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="fonds", description="Переглянути фонд сервера та зробити внесок")
    async def fonds_cmd(self, interaction: discord.Interaction):
        from modules.db import get_guild_settings

        settings = await get_guild_settings(db, interaction.guild.id)
        eco = get_eco(settings)

        if not eco.get("enabled", True):
            return await interaction.response.send_message(f"{E_CROSS} Економіка вимкнена.", ephemeral=True)

        if not eco.get("fund_enabled", False):
            return await interaction.response.send_message(f"{E_CROSS} Фонд сервера наразі вимкнений.", ephemeral=True)

        await interaction.response.send_message(embed=build_fund_embed(eco, interaction.guild), view=FundView(eco))


async def setup(bot):
    await bot.add_cog(FondsCommand(bot))
