import io
import logging
from datetime import datetime, timedelta

import discord
import matplotlib
import matplotlib.pyplot as plt
from discord import app_commands
from discord.ext import commands

from modules.db import get_database
from repositories.user import get_level_xp, get_user
from utils.ui_contract import add_section, set_surface_footer, surface_embed

matplotlib.rcParams["axes.unicode_minus"] = False

_log = logging.getLogger("profile")
db = get_database()

E_CHAT = "<:chat:1485608210202361976>"
E_MICRO = "<:micro:1485608331484729344>"
E_STAR = "<:star:1485626121847574631>"
E_CALENDAR = "<:info:1485638054201921536>"
E_COIN = "<:coin:1485610808003133552>"
E_FLAME = "<:flame:1485618663489929356>"
E_SHIELD = "<:shield:1485606277081071666>"
E_BOOST = "<:boost:1485610043033518131>"
E_BANK = "<:bank_safe:1485637217132216571>"


def make_xp_bar(xp: int, needed: int, length: int = 8) -> str:
    if needed <= 0:
        return "█" * length
    filled = round((xp / needed) * length)
    filled = max(0, min(filled, length))
    return "█" * filled + "░" * (length - filled)


class ProfileCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Показує профіль користувача")
    @app_commands.describe(user="Користувач (за замовчуванням — ти)")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=False)
        except Exception:
            pass

        try:
            target = user or interaction.user
            data = await get_user(db, interaction.guild.id, target.id)

            level = data.get("level", 1)
            xp = data.get("xp", 0)
            xp_needed = get_level_xp(level)
            xp_bar = make_xp_bar(xp, xp_needed)
            voice_h = round(data.get("voice_minutes", 0) / 60, 1)
            msgs = data.get("messages", 0)
            reactions = data.get("reactions", 0)
            joined_at = target.joined_at.strftime("%d %B %Y") if target.joined_at else "Невідомо"

            roles = [
                role.name
                for role in sorted(target.roles, key=lambda role: role.position, reverse=True)
                if role.name != "@everyone"
            ][:3]
            roles_str = ", ".join(roles) if roles else "Немає"

            history = data.get("history", {})
            days = [datetime.now() - timedelta(days=index) for index in reversed(range(7))]
            labels = [day.strftime("%a") for day in days]
            values = [history.get(day.strftime("%Y-%m-%d"), 0) for day in days]

            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(labels, values, marker="o", linestyle="-", color="royalblue", linewidth=2)
            ax.set_title("Активність (XP за останні 7 днів)", fontsize=11)
            ax.set_xlabel("День тижня")
            ax.set_ylabel("Отримано XP")
            ax.grid(True, color="darkgray", alpha=0.5)
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)

            filename = "profile_graph.png"
            file = discord.File(fp=buf, filename=filename)

            total_xp_val = sum(get_level_xp(level_index) for level_index in range(1, level)) + xp
            wallet = data.get("wallet", 0)
            bank = data.get("bank", 0)
            streak = data.get("daily_streak", 0)
            quests = data.get("completed_quests", 0)

            now = datetime.now()
            shield_until = data.get("shield_until")
            boost_until = data.get("coin_boost_until")

            active_items = []
            if shield_until and isinstance(shield_until, datetime) and shield_until > now:
                active_items.append(f"{E_SHIELD} Щит до <t:{int(shield_until.timestamp())}:R>")
            if boost_until and isinstance(boost_until, datetime) and boost_until > now:
                active_items.append(f"{E_BOOST} Буст до <t:{int(boost_until.timestamp())}:R>")

            embed = surface_embed(
                "gameplay",
                title=f"Профіль {target.display_name}",
                description=(
                    f"{E_CALENDAR} **Учасник з:** {joined_at}\n"
                    f"**Рівень:** {level}\n"
                    f"`{xp_bar}` {xp}/{xp_needed} XP\n"
                    f"Загальний XP: **{total_xp_val:,}**"
                ),
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            add_section(
                embed,
                "Активність",
                [
                    f"{E_CHAT} Повідомлення: **{msgs}**",
                    f"{E_MICRO} Голос: **{voice_h} год**",
                    f"{E_STAR} Реакції: **{reactions}**",
                    f"**Ролі:** {roles_str}",
                ],
                inline=True,
            )
            add_section(
                embed,
                "<:coins:1485612564619727011> Економіка",
                [
                    f"{E_COIN} Гаманець: **{wallet:,}**",
                    f"{E_BANK} Банк: **{bank:,}**",
                    f"{E_FLAME} Стрік: **{streak}** днів",
                    f"<:check:1485597845883981905> Квестів: **{quests}**",
                ],
                inline=True,
            )
            add_section(
                embed,
                "<:boost:1485610043033518131> Активно",
                active_items or ["Немає активних бонусів."],
                inline=False,
            )
            embed.set_image(url=f"attachment://{filename}")
            set_surface_footer(embed, "gameplay", "Профіль поєднує XP, економіку і поточні бонуси.")

            await interaction.followup.send(embed=embed, file=file)

        except discord.HTTPException as exc:
            await interaction.followup.send(f"<:warning:1485598476850040843> Помилка Discord: `{exc}`")
        except Exception as exc:
            _log.error("Unexpected profile error for %s: %s", target, exc, exc_info=True)
            await interaction.followup.send("<:warning:1485598476850040843> Внутрішня помилка. Спробуйте пізніше.")


async def setup(bot):
    await bot.add_cog(ProfileCommands(bot))
