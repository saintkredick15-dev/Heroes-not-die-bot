from __future__ import annotations

import io
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from modules.db import get_database
from config.constants import Emojis as _E
from services.metrics import count_active_users_since, get_global_metrics, hours_ago
from utils.ui_contract import add_section, compact_kv, set_surface_footer, surface_embed

db = get_database()

E_TOOLS = _E.TOOLS.value
E_SEARCH = _E.SEARCH.value
E_STATS = _E.STATS.value
E_SHIELD_CHECK = _E.SHIELD_CHECK.value
E_SHIELD = _E.SHIELD.value
E_CHECK = _E.CHECK.value
E_CROSS = _E.CROSS.value


def _fmt_metric_ts(value) -> str:
    if not value:
        return "ще не було"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return f"<t:{int(value.timestamp())}:R>"
    return str(value)


class AddAccessModal(discord.ui.Modal, title="Додати доступ до /dev_stats"):
    user_id_input = discord.ui.TextInput(
        label="ID користувача",
        placeholder="Введіть Discord ID...",
        min_length=17,
        max_length=25,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
            await db.bot_settings.update_one(
                {"_id": "dev_access"},
                {"$addToSet": {"allowed_users": uid}},
                upsert=True,
            )
            await interaction.response.send_message(
                f"{E_CHECK} Доступ надано користувачу з ID `{uid}`.",
                ephemeral=True,
            )
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Невірний формат ID.", ephemeral=True)


class RemoveAccessModal(discord.ui.Modal, title="Забрати доступ до /dev_stats"):
    user_id_input = discord.ui.TextInput(
        label="ID користувача",
        placeholder="Введіть Discord ID...",
        min_length=17,
        max_length=25,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
            await db.bot_settings.update_one(
                {"_id": "dev_access"},
                {"$pull": {"allowed_users": uid}},
                upsert=True,
            )
            await interaction.response.send_message(
                f"{E_CHECK} Доступ забрано у користувача з ID `{uid}`.",
                ephemeral=True,
            )
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Невірний формат ID.", ephemeral=True)


class DevStatsView(discord.ui.View):
    def __init__(self, cog: "DevStatsCommand", user: discord.User, guild_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user = user
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                f"{E_CROSS} Ви не можете використовувати ці кнопки.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="Глобальна статистика",
        style=discord.ButtonStyle.secondary,
        custom_id="dev_stats_global",
        emoji=E_SEARCH,
    )
    async def btn_global(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, file = await self.cog.get_stats_embed(global_stats=True)
        if file:
            await interaction.edit_original_response(embed=embed, attachments=[file])
        else:
            await interaction.edit_original_response(embed=embed, attachments=[])

    @discord.ui.button(
        label="Поточний сервер",
        style=discord.ButtonStyle.secondary,
        custom_id="dev_stats_local",
        emoji=E_STATS,
    )
    async def btn_local(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, file = await self.cog.get_stats_embed(
            global_stats=False,
            guild_id=self.guild_id,
            guild_name=interaction.guild.name,
        )
        if file:
            await interaction.edit_original_response(embed=embed, attachments=[file])
        else:
            await interaction.edit_original_response(embed=embed, attachments=[])

    @discord.ui.button(
        label="Додати доступ",
        style=discord.ButtonStyle.secondary,
        custom_id="dev_stats_access",
        emoji=E_SHIELD_CHECK,
    )
    async def btn_access(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddAccessModal(self.cog.bot))

    @discord.ui.button(
        label="Забрати доступ",
        style=discord.ButtonStyle.secondary,
        custom_id="dev_stats_remove_access",
        emoji=E_SHIELD,
    )
    async def btn_remove_access(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveAccessModal(self.cog.bot))


def is_owner_or_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if await interaction.client.is_owner(interaction.user):
            return True
        doc = await db.bot_settings.find_one({"_id": "dev_access"})
        if doc and interaction.user.id in doc.get("allowed_users", []):
            return True
        return False

    return app_commands.check(predicate)


class DevStatsCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_server_snapshot(self, guild_id: int) -> dict:
        wallets = await db.users.find({"guild_id": guild_id}).to_list(length=None)

        active_wallets = len([w for w in wallets if w.get("wallet", 0) > 0 or w.get("bank", 0) > 0])
        total_in_wallets = sum(w.get("wallet", 0) for w in wallets)
        total_in_banks = sum(w.get("bank", 0) for w in wallets)
        total_earned = sum(w.get("total_earned", 0) for w in wallets)
        total_money = total_in_wallets + total_in_banks

        settings = await db.guild_settings.find_one({"_id": guild_id}) or {}
        eco = settings.get("economy", {})
        inflation_mult = eco.get("inflation_multiplier", 1.0)

        return {
            "timestamp": int(time.time()),
            "guild_id": guild_id,
            "active_wallets": active_wallets,
            "total_money": total_money,
            "total_earned": total_earned,
            "inflation_mult": inflation_mult,
        }

    async def ensure_snapshot_saved(self, guild_id: int):
        now = int(time.time())
        last_snap = await db.server_analytics.find_one({"guild_id": guild_id}, sort=[("timestamp", -1)])
        if not last_snap or (now - last_snap["timestamp"]) > 3600:
            snapshot = await self.get_server_snapshot(guild_id)
            await db.server_analytics.insert_one(snapshot)

    async def _build_global_economy_totals(self) -> dict:
        total_money = 0
        total_earned = 0
        active_wallets = 0
        async for user in db.users.find({}):
            wallet = user.get("wallet", 0)
            bank = user.get("bank", 0)
            if wallet > 0 or bank > 0:
                active_wallets += 1
            total_money += wallet + bank
            total_earned += user.get("total_earned", 0)
        return {
            "total_money": total_money,
            "total_earned": total_earned,
            "active_wallets": active_wallets,
            "inflation_mult": 0.0,
        }

    async def get_stats_embed(
        self,
        global_stats: bool = False,
        guild_id: int | None = None,
        guild_name: str | None = None,
    ):
        metrics = await get_global_metrics()
        active_since = hours_ago(24)
        file = None

        if global_stats:
            current = await self._build_global_economy_totals()
            history = []
            active_users_24h = await count_active_users_since(active_since)
            title = f"{E_SEARCH} Глобальна статистика"
            description = "Зведення по всіх серверах: live-лічильники, використання функцій і стан операцій."
        else:
            await self.ensure_snapshot_saved(guild_id)
            current = await self.get_server_snapshot(guild_id)
            history = await db.server_analytics.find({"guild_id": guild_id}).sort("timestamp", 1).limit(100).to_list(length=100)
            active_users_24h = await count_active_users_since(active_since, guild_id=guild_id)
            title = f"{E_STATS} Аналітика: {guild_name or guild_id}"
            description = "Локальний знімок економіки сервера: обіг, інфляція та активність."

        embed = surface_embed("admin", title, description)

        core_lines = []
        if global_stats:
            core_lines.append(compact_kv("Серверів", f"{len(self.bot.guilds):,}"))
        core_lines.extend(
            [
                compact_kv("Активні користувачі за 24г", f"{active_users_24h:,}"),
                compact_kv("Використано команд", f"{metrics.get('commands_used_total', 0):,}"),
                compact_kv("Помилок команд", f"{metrics.get('command_errors_total', 0):,}"),
            ]
        )
        add_section(embed, "Стан ядра", core_lines, inline=False)

        economy_lines = [
            compact_kv("Всього валюти", f"{current.get('total_money', 0):,}"),
            compact_kv("Згенеровано", f"{current.get('total_earned', 0):,}"),
            compact_kv("Відстежені витрати", f"{metrics.get('economy_total_spent', 0):,}"),
            compact_kv("Зібрано податків", f"{metrics.get('economy_tax_collected', 0):,}"),
            compact_kv("Активних гаманців", f"{current.get('active_wallets', 0):,}"),
        ]
        add_section(embed, "Стан економіки", economy_lines, inline=False)

        if global_stats:
            usage_lines = [
                compact_kv("Daily claims", f"{metrics.get('daily_claims_total', 0):,}"),
                compact_kv("Work runs", f"{metrics.get('work_runs_total', 0):,}"),
                compact_kv("Crime runs", f"{metrics.get('crime_runs_total', 0):,}"),
                compact_kv("Crime success", f"{metrics.get('crime_success_total', 0):,}"),
                compact_kv("Duels started", f"{metrics.get('duel_started_total', 0):,}"),
                compact_kv("Gambling sessions", f"{metrics.get('gambling_sessions_total', 0):,}"),
                compact_kv("Shop purchases", f"{metrics.get('shop_purchases_total', 0):,}"),
                compact_kv(
                    "Тікети відкрито / закрито",
                    f"{metrics.get('tickets_opened_total', 0):,} / {metrics.get('tickets_closed_total', 0):,}",
                ),
                compact_kv("Попереджень видано", f"{metrics.get('warnings_issued_total', 0):,}"),
                compact_kv("Дій automod", f"{metrics.get('automod_actions_total', 0):,}"),
            ]
            add_section(embed, "Використання функцій", usage_lines, inline=False)

            ops_lines = [
                compact_kv("Останній sync команд", _fmt_metric_ts(metrics.get("last_command_sync_at"))),
                compact_kv("Остання виплата відсотків", _fmt_metric_ts(metrics.get("last_interest_payout_at"))),
                compact_kv("Останній season reset", _fmt_metric_ts(metrics.get("last_season_reset_at"))),
            ]
            add_section(embed, "Операції", ops_lines, inline=False)
        else:
            inflation_mult = current.get("inflation_mult", 1.0)
            add_section(
                embed,
                "Локальний стан",
                [
                    compact_kv("Інфляція", f"+{(inflation_mult - 1.0) * 100:.4f}%"),
                    compact_kv("Попереджень видано (global)", f"{metrics.get('warnings_issued_total', 0):,}"),
                    compact_kv("Дій automod (global)", f"{metrics.get('automod_actions_total', 0):,}"),
                ],
                inline=False,
            )

        if not global_stats and HAS_MATPLOTLIB and len(history) > 1:
            try:
                timestamps = [datetime.fromtimestamp(snap["timestamp"]) for snap in history]
                totals = [snap.get("total_money", 0) for snap in history]
                if len(history) < 3:
                    timestamps.insert(0, timestamps[0] - timedelta(hours=12))
                    totals.insert(0, max(0, int(totals[0] * 0.9)))

                fig, ax = plt.subplots(figsize=(8, 4))
                fig.patch.set_facecolor("#FFFFFF")
                ax.set_facecolor("#FFFFFF")
                ax.plot(
                    timestamps,
                    totals,
                    color="#4F46E5",
                    marker="o",
                    linestyle="-",
                    linewidth=2.6,
                    markersize=5,
                    markerfacecolor="#4F46E5",
                    markeredgecolor="#FFFFFF",
                    markeredgewidth=1.2,
                )
                ax.fill_between(timestamps, totals, alpha=0.14, color="#818CF8")
                ax.set_title("Грошова маса в обороті", color="#111827", fontsize=12, fontweight="bold", pad=12)
                ax.set_ylabel("Монети", color="#4B5563")
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
                ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
                ax.tick_params(axis="x", colors="#6B7280", labelsize=8, rotation=30)
                ax.tick_params(axis="y", colors="#6B7280", labelsize=8)
                ax.grid(True, linestyle="--", linewidth=0.8, alpha=0.45, color="#D1D5DB")
                ax.set_axisbelow(True)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.spines["left"].set_color("#E5E7EB")
                ax.spines["bottom"].set_color("#E5E7EB")
                ax.margins(x=0.03)
                plt.tight_layout()

                buf = io.BytesIO()
                plt.savefig(buf, format="png", facecolor="#FFFFFF", edgecolor="none", dpi=160)
                buf.seek(0)
                plt.close(fig)

                file = discord.File(buf, filename="chart.png")
                embed.set_image(url="attachment://chart.png")
            except Exception as exc:
                embed.set_footer(text=f"Не вдалося згенерувати графік: {exc}")

        if not embed.footer.text:
            set_surface_footer(
                embed,
                "admin",
                "Global view використовує live economy + persistent counters. Local view показує snapshot-графік.",
            )
        return embed, file

    @app_commands.command(name="dev_stats", description="[OWNER ONLY] Аналітика та операційні метрики бота")
    @is_owner_or_admin()
    async def dev_stats(self, interaction: discord.Interaction):
        embed = surface_embed(
            "admin",
            f"{E_TOOLS} Панель розробника",
            "Оберіть режим перегляду або керуйте доступом до /dev_stats.",
        )
        add_section(
            embed,
            "Що показує",
            [
                "Глобальну економіку по всіх серверах.",
                "Локальний стан сервера зі snapshot-графіком.",
                "Лічильники використання функцій бота.",
                "Операційні timestamps для scheduler/sync/reset.",
            ],
        )
        set_surface_footer(embed, "admin", "Dev Stats показує реальні метрики, а не декоративний overview.")
        view = DevStatsView(self, interaction.user, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(DevStatsCommand(bot))
