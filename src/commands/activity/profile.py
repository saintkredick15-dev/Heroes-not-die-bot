import io
import logging
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['axes.unicode_minus'] = False

from modules.db import get_database
from repositories.user import get_user, get_level_xp

_log = logging.getLogger("profile")
db = get_database()

# ── Кастомні емодзі ──────────────────────────────────────────────────────────
E_CHAT     = "<:chat:1475953787687403716>"
E_MICRO    = "<:micro:1475954046350135346>"
E_STAR     = "<:star:1475954213455532067>"
E_CALENDAR = "<:calendar:1476195260236435608>"
E_COIN     = "<:coin:1478487028105482485>"
E_FLAME    = "<:flame:1478490474145906800>"
E_SHIELD   = "<:shield:1478800925664612372>"
E_BOOST    = "<:boost:1478073594247643377>"
E_BANK     = "<:bank:1478483868867891261>"

EMBED_COLOR = 0x1a1a2e

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
            target    = user or interaction.user
            data      = await get_user(db, interaction.guild.id, target.id)

            level     = data.get("level", 1)
            xp        = data.get("xp", 0)
            xp_needed = get_level_xp(level)
            xp_bar    = make_xp_bar(xp, xp_needed)
            voice_h   = round(data.get("voice_minutes", 0) / 60, 1)
            msgs      = data.get("messages", 0)
            reactions = data.get("reactions", 0)
            joined_at = (
                target.joined_at.strftime("%d %B %Y")
                if target.joined_at else "Невідомо"
            )

            roles = [
                r.name for r in sorted(target.roles, key=lambda r: r.position, reverse=True)
                if r.name != "@everyone"
            ][:3]
            roles_str = ", ".join(roles) if roles else "Немає"

            # ── Графік (білий фон — як оригінальна версія) ──────────────────
            history = data.get("history", {})
            days    = [datetime.now() - timedelta(days=i) for i in reversed(range(7))]
            labels  = [d.strftime("%a") for d in days]
            values  = [history.get(d.strftime("%Y-%m-%d"), 0) for d in days]

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
            file     = discord.File(fp=buf, filename=filename)

            total_xp_val = sum(get_level_xp(l) for l in range(1, level)) + xp
            
            eco_user = await db.economy_users.find_one({"guild_id": interaction.guild.id, "user_id": target.id}) or {}
            wallet = eco_user.get("wallet", 0)
            bank   = eco_user.get("bank", 0)
            streak = eco_user.get("daily_streak", 0)
            quests = eco_user.get("completed_quests", 0)
            
            now = datetime.now()
            shield_until = eco_user.get("shield_until")
            boost_until  = eco_user.get("coin_boost_until")
            
            active_items = []
            if shield_until and isinstance(shield_until, datetime) and shield_until > now:
                active_items.append(f"{E_SHIELD} Щит до <t:{int(shield_until.timestamp())}:R>")
            if boost_until and isinstance(boost_until, datetime) and boost_until > now:
                active_items.append(f"{E_BOOST} Буст до <t:{int(boost_until.timestamp())}:R>")
                
            eco_str = (
                f"<:Wallet:1478483324392706201>Гаманець: **{wallet:,}** {E_COIN}\n"
                f":bank: Банк: **{bank:,}**<:banknote:1478511186860572753>\n"
                f"{E_FLAME} Стрік: **{streak}** днів\n"
                f"<:cutiecheckmark:1479120440734650389> Квестів: **{quests}**"
            )
            active_str = "\n".join(active_items) if active_items else "Немає активних бонусів."

            # ── Embed — вертикальний layout як у v1, але з новим стилем ─────
            embed = discord.Embed(
                title=f"Профіль {target.display_name}",
                color=EMBED_COLOR,
            )
            embed.set_thumbnail(url=target.display_avatar.url)  
            embed.description = "\n".join([
                f"{E_CALENDAR} **Учасник з:** {joined_at}\n",
                f"**Рівень:** {level}",
                f"`{xp_bar}` {xp}/{xp_needed} XP",
                f"Загальний XP: **{total_xp_val:,}**\n",
                f"{E_CHAT} {msgs}　{E_MICRO} {voice_h}г　{E_STAR} {reactions}\n",
                f"**Ролі:** {roles_str}",
            ])
            embed.add_field(name="<:Coins:1478486725113286899> Економіка", value=eco_str, inline=True)
            embed.add_field(name="<:zap:1479582544361033820> Активно", value=active_str, inline=True)
            embed.set_image(url=f"attachment://{filename}")

            await interaction.followup.send(embed=embed, file=file)

        except discord.HTTPException as e:
            await interaction.followup.send(f"⚠️ Помилка Discord: `{e}`")
        except Exception as e:
            _log.error("Unexpected profile error for %s: %s", target, e, exc_info=True)
            await interaction.followup.send("⚠️ Внутрішня помилка. Спробуйте пізніше.")

async def setup(bot):
    await bot.add_cog(ProfileCommands(bot))
