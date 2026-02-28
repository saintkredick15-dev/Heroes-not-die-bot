from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
from repositories.user import get_level_xp

db = get_database()

# ── Кастомні емодзі сервера ─────────────────────────────────────────────────
EMOJI_TROPHY = "<:trophy:1475953207782932602>"
EMOJI_MEDAL  = "<:medal:1475953523039408360>"
EMOJI_CHAT   = "<:chat:1475953787687403716>"
EMOJI_MICRO  = "<:micro:1475954046350135346>"
EMOJI_STAR   = "<:star:1475954213455532067>"
EMOJI_NEXT   = "<:vpravo:1475954959555235882>"
EMOJI_PREV   = "<:vlivo:1475954870027681952>"

# Топ-3 відзнаки (позиція → емодзі)
RANK_BADGES = {1: EMOJI_TROPHY, 2: EMOJI_MEDAL, 3: EMOJI_STAR}

PAGE_SIZE = 10  # юзерів на сторінку


def make_xp_bar(xp: int, needed: int, length: int = 8) -> str:
    """Прогрес-бар XP: ████░░░░ (clamp: ніколи не перевищує length)"""
    if needed <= 0:
        return "█" * length
    filled = max(0, min(length, round((xp / needed) * length)))
    return "█" * filled + "░" * (length - filled)


async def fetch_leaderboard(guild: discord.Guild) -> list[tuple[int, dict, discord.Member]]:
    """
    Відсортований список (rank, user_data, member) тільки для тих,
    хто реально є на сервері. Сортування на рівні MongoDB. Ліміт 200.
    """
    cursor = db.users.find({"guild_id": guild.id}).sort(
        [("level", -1), ("xp", -1)]
    ).limit(200)

    results: list[tuple[int, dict, discord.Member]] = []
    rank = 0
    async for doc in cursor:
        member = guild.get_member(doc.get("user_id", 0))
        if not member:
            continue
        rank += 1
        results.append((rank, doc, member))
    return results


def build_embed(
    entries: list[tuple[int, dict, discord.Member]],
    page: int,
    total_pages: int,
    guild_icon: str | None,
    author_rank: int | None,
    author_data: dict | None,
) -> discord.Embed:
    start = page * PAGE_SIZE
    page_entries = entries[start : start + PAGE_SIZE]

    embed = discord.Embed(color=0x1a1a2e)
    embed.set_author(
        name=f"LEADERBOARD  •  {page + 1}/{total_pages}",
        icon_url=guild_icon,
    )

    lines: list[str] = []
    for rank, doc, member in page_entries:
        level   = doc.get("level", 1)
        xp      = doc.get("xp", 0)
        needed  = get_level_xp(level)
        bar     = make_xp_bar(xp, needed)
        msgs    = doc.get("messages", 0)
        voice_h = round(doc.get("voice_minutes", 0) / 60, 1)
        reactions = doc.get("reactions", 0)

        badge = RANK_BADGES.get(rank, f"`{rank:>2}.`")
        name  = member.display_name[:20]

        lines.append(
            f"{badge} **{name}** — Lv.{level}\n"
            f"　`{bar}` {xp}/{needed} XP\n"
            f"　{EMOJI_CHAT} {msgs}  {EMOJI_MICRO} {voice_h}г  {EMOJI_STAR} {reactions}"
        )

    embed.description = "\n\n".join(lines) if lines else "*Тут поки нікого немає*"

    # Позиція автора — ЗАВЖДИ в footer на кожній сторінці
    if author_rank and author_data:
        a_level   = author_data.get("level", 1)
        a_xp      = author_data.get("xp", 0)
        a_needed  = get_level_xp(a_level)
        a_bar     = make_xp_bar(a_xp, a_needed)
        a_msgs    = author_data.get("messages", 0)
        a_voice_h = round(author_data.get("voice_minutes", 0) / 60, 1)
        embed.set_footer(
            text=(
                f"Ти на #{author_rank} • Lv.{a_level} • "
                f"{a_bar} {a_xp}/{a_needed} XP • "
                f"{EMOJI_CHAT} {a_msgs}  {EMOJI_MICRO} {a_voice_h}г"
            ),
        )

    return embed


class LeaderboardView(discord.ui.View):
    def __init__(
        self,
        entries: list[tuple[int, dict, discord.Member]],
        guild: discord.Guild,
        author_id: int,
    ):
        super().__init__(timeout=600)  # 10 хвилин
        self.entries      = entries
        self.guild        = guild
        self.author_id    = author_id
        self.page         = 0
        self.total_pages  = max(1, -(-len(entries) // PAGE_SIZE))  # ceil div
        self.message: discord.Message | None = None  # зберігаємо для on_timeout

        # Знаходимо позицію автора
        self.author_rank: int | None  = None
        self.author_data: dict | None = None
        for rank, doc, member in entries:
            if doc.get("user_id") == author_id:
                self.author_rank = rank
                self.author_data = doc
                break

        self._update_buttons()

    async def on_timeout(self) -> None:
        """Вимикаємо кнопки після 2 хв — щоб не було 'взаємодія не вдалась'."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass  # повідомлення вже видалено

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Це не твоя команда.", ephemeral=True
            )
            return False
        return True

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total_pages - 1

    def build(self) -> discord.Embed:
        return build_embed(
            self.entries,
            self.page,
            self.total_pages,
            self.guild.icon.url if self.guild.icon else None,
            self.author_rank,
            self.author_data,
        )

    @discord.ui.button(
        emoji=discord.PartialEmoji.from_str("<:vlivo:1475954870027681952>"),
        style=discord.ButtonStyle.secondary,
        custom_id="lb_prev",
    )
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)

    @discord.ui.button(
        emoji=discord.PartialEmoji.from_str("<:vpravo:1475954959555235882>"),
        style=discord.ButtonStyle.secondary,
        custom_id="lb_next",
    )
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)


class LeaderboardCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Показує топ користувачів сервера")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        entries = await fetch_leaderboard(interaction.guild)

        if not entries:
            await interaction.followup.send(
                "📭 На сервері ще немає статистики.", ephemeral=True
            )
            return

        view = LeaderboardView(entries, interaction.guild, interaction.user.id)
        # followup.send повертає Message — зберігаємо щоб on_timeout міг редагувати
        msg = await interaction.followup.send(embed=view.build(), view=view, wait=True)
        view.message = msg


async def setup(bot):
    await bot.add_cog(LeaderboardCommands(bot))