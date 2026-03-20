from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
from repositories.user import get_level_xp

db = get_database()

# ── Кастомні емодзі ───────────────────────────────────────────────────────────
EMOJI_TROPHY = "<:trophy:1475953207782932602>"
EMOJI_MEDAL  = "<:medal:1475953523039408360>"
EMOJI_CHAT   = "<:chat:1475953787687403716>"
EMOJI_MICRO  = "<:micro:1475954046350135346>"
EMOJI_STAR   = "<:star:1475954213455532067>"
EMOJI_NEXT   = "<:vpravo:1475954959555235882>"
EMOJI_PREV   = "<:vlivo:1475954870027681952>"
EMOJI_COIN   = "<:coin:1478487028105482485>"
EMOJI_BANK   = "<:bank:1478483868867891261>"
EMOJI_STATS  = "<:statistics:1477721796857041067>"

RANK_BADGES = {1: EMOJI_TROPHY, 2: EMOJI_MEDAL, 3: EMOJI_STAR}
PAGE_SIZE   = 10

def make_xp_bar(xp: int, needed: int, length: int = 8) -> str:
    if needed <= 0:
        return "█" * length
    filled = max(0, min(length, round((xp / needed) * length)))
    return "█" * filled + "░" * (length - filled)

# ── XP Leaderboard ────────────────────────────────────────────────────────────

async def fetch_xp_leaderboard(guild: discord.Guild) -> list[tuple[int, dict, discord.Member]]:
    cursor = db.users.find({"guild_id": guild.id}).sort([("level", -1), ("xp", -1)]).limit(200)
    results: list[tuple[int, dict, discord.Member]] = []
    rank = 0
    async for doc in cursor:
        member = guild.get_member(doc.get("user_id", 0))
        if not member:
            continue
        rank += 1
        results.append((rank, doc, member))
    return results

async def fetch_xp_week(guild: discord.Guild) -> list[tuple[int, dict, discord.Member]]:
    cursor = db.users.find({"guild_id": guild.id, "xp_week": {"$gt": 0}}).sort("xp_week", -1).limit(200)
    results = []
    rank = 0
    async for doc in cursor:
        member = guild.get_member(doc.get("user_id", 0))
        if not member or member.bot:
            continue
        rank += 1
        results.append((rank, doc, member))
    return results

async def fetch_xp_month(guild: discord.Guild) -> list[tuple[int, dict, discord.Member]]:
    cursor = db.users.find({"guild_id": guild.id, "xp_month": {"$gt": 0}}).sort("xp_month", -1).limit(200)
    results = []
    rank = 0
    async for doc in cursor:
        member = guild.get_member(doc.get("user_id", 0))
        if not member or member.bot:
            continue
        rank += 1
        results.append((rank, doc, member))
    return results

def build_xp_embed(
    entries: list[tuple[int, dict, discord.Member]],
    page: int,
    total_pages: int,
    guild_icon: str | None,
    author_rank: int | None,
    author_data: dict | None,
    mode: str = "all",
) -> discord.Embed:
    start        = page * PAGE_SIZE
    page_entries = entries[start: start + PAGE_SIZE]
    embed        = discord.Embed(color=0x1a1a2e)
    mode_label = {"week": "ТИЖДЕНЬ", "month": "МІСЯЦЬ", "all": "ALL TIME"}.get(mode, "ALL TIME")
    embed.set_author(name=f"LEADERBOARD  •  XP  •  {mode_label}  •  {page + 1}/{total_pages}", icon_url=guild_icon)

    lines: list[str] = []
    for rank, doc, member in page_entries:
        level    = doc.get("level", 1)
        xp       = doc.get("xp", 0)
        needed   = get_level_xp(level)
        badge    = RANK_BADGES.get(rank, f"`{rank:>2}.`")
        name     = member.display_name[:20]

        if mode == "week":
            xp_period = doc.get("xp_week", 0)
            bar = make_xp_bar(xp_period, max(xp_period, 1))
            lines.append(
                f"{badge} **{name}** — Lv.{level}\n"
                f"　`{bar}` +{xp_period} XP цього тижня"
            )
        elif mode == "month":
            xp_period = doc.get("xp_month", 0)
            bar = make_xp_bar(xp_period, max(xp_period, 1))
            lines.append(
                f"{badge} **{name}** — Lv.{level}\n"
                f"　`{bar}` +{xp_period} XP цього місяця"
            )
        else:
            bar      = make_xp_bar(xp, needed)
            msgs     = doc.get("messages", 0)
            voice_h  = round(doc.get("voice_minutes", 0) / 60, 1)
            reactions = doc.get("reactions", 0)
            lines.append(
                f"{badge} **{name}** — Lv.{level}\n"
                f"　`{bar}` {xp}/{needed} XP\n"
                f"　{EMOJI_CHAT} {msgs}  {EMOJI_MICRO} {voice_h}г  {EMOJI_STAR} {reactions}"
            )

    embed.description = "\n\n".join(lines) if lines else "*Тут поки нікого немає*"

    if author_rank and author_data:
        a_level  = author_data.get("level", 1)
        a_xp     = author_data.get("xp", 0)
        a_needed = get_level_xp(a_level)
        embed.set_footer(text=f"Ти на #{author_rank} • Lv.{a_level} • {a_xp}/{a_needed} XP")
    return embed

# ── Economy Leaderboard ───────────────────────────────────────────────────────

async def fetch_eco_leaderboard(guild: discord.Guild) -> list[tuple[int, dict, discord.Member]]:
    cursor = db.users.find({"guild_id": guild.id}).limit(300)
    raw: list[tuple[int, dict, discord.Member]] = []
    async for doc in cursor:
        member = guild.get_member(doc.get("user_id", 0))
        if not member:
            continue
        total_wealth = doc.get("wallet", 0) + doc.get("bank", 0)
        raw.append((total_wealth, doc, member))

    raw.sort(key=lambda x: x[0], reverse=True)
    results = []
    for rank, (wealth, doc, member) in enumerate(raw, start=1):
        results.append((rank, doc, member))
    return results

def build_eco_embed(
    entries: list[tuple[int, dict, discord.Member]],
    page: int,
    total_pages: int,
    guild_icon: str | None,
    author_rank: int | None,
    author_data: dict | None,
    eco_settings: dict,
    mode: str = "all"
) -> discord.Embed:
    start        = page * PAGE_SIZE
    page_entries = entries[start: start + PAGE_SIZE]
    curr         = eco_settings.get("currency_emoji", EMOJI_COIN)
    curr_name    = eco_settings.get("currency_name", "Coin")
    embed        = discord.Embed(color=0x1a1a2e)
    
    title_mode = {"week": "7 ДНІВ", "month": "30 ДНІВ", "all": "ALL TIME"}.get(mode, "ALL TIME")
    embed.set_author(name=f"LEADERBOARD  •  ECONOMY  •  {title_mode}  •  {page + 1}/{total_pages}", icon_url=guild_icon)

    lines: list[str] = []
    for rank, doc, member in page_entries:
        badge = RANK_BADGES.get(rank, f"`{rank:>2}.`")
        name  = member.display_name[:20]

        if mode == "week":
            earned = doc.get("week_earned", 0)
            lines.append(f"{badge} **{name}** — Зароблено: `{earned:,}` {curr}")
        elif mode == "month":
            earned = doc.get("month_earned", 0)
            lines.append(f"{badge} **{name}** — Зароблено: `{earned:,}` {curr}")
        else:
            wallet = doc.get("wallet", 0)
            bank   = doc.get("bank", 0)
            total  = wallet + bank
            lines.append(
                f"{badge} **{name}** — `{total:,}` {curr}\n"
                f"　{EMOJI_COIN} `{wallet:,}`  {EMOJI_BANK} `{bank:,}`"
            )

    embed.description = "\n\n".join(lines) if lines else "*Тут поки нікого немає*"

    if author_rank and author_data:
        if mode == "week":
            a_val = author_data.get("week_earned", 0)
        elif mode == "month":
            a_val = author_data.get("month_earned", 0)
        else:
            a_val = author_data.get("wallet", 0) + author_data.get("bank", 0)
        embed.set_footer(text=f"Ти на #{author_rank} \u2022 {a_val:,} {curr_name}")
    return embed

def build_history_embed(
    history_entries: list[dict],
    page: int,
    total_pages: int,
    guild_icon: str | None,
    eco_settings: dict,
    guild: discord.Guild
) -> discord.Embed:
    start = page * PAGE_SIZE
    page_entries = history_entries[start: start + PAGE_SIZE]
    curr = eco_settings.get("currency_emoji", EMOJI_COIN)
    embed = discord.Embed(color=0x1a1a2e)
    embed.set_author(name=f"LEADERBOARD  •  ECONOMY  •  HISTORY  •  {page + 1}/{total_pages}", icon_url=guild_icon)

    lines = []
    for h in page_entries:
        season = h.get("season", 1)
        date = h.get("date", 0)
        top3 = h.get("top3", [])
        
        lines.append(f"**Сезон {season}** — <t:{date}:d>")
        for i, t in enumerate(top3, start=1):
            user_id = t.get("user_id")
            earned = t.get("earned", 0)
            member = guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            badge = RANK_BADGES.get(i, f"`{i}.`")
            lines.append(f"　{badge} **{name}** — `{earned:,}` {curr}")
        lines.append("")

    embed.description = "\n".join(lines).strip() if lines else "*Історія сезонів порожня*"
    return embed

async def fetch_eco_week(guild: discord.Guild):
    """Top by week_earned."""
    cursor = db.users.find({"guild_id": guild.id}).sort("week_earned", -1).limit(200)
    results = []
    rank = 0
    async for doc in cursor:
        member = guild.get_member(doc.get("user_id", 0))
        if not member or member.bot:
            continue
        if doc.get("week_earned", 0) <= 0:
            continue
        rank += 1
        results.append((rank, doc, member))
    return results

async def fetch_eco_month(guild: discord.Guild):
    """Top by month_earned."""
    cursor = db.users.find({"guild_id": guild.id}).sort("month_earned", -1).limit(200)
    results = []
    rank = 0
    async for doc in cursor:
        member = guild.get_member(doc.get("user_id", 0))
        if not member or member.bot:
            continue
        if doc.get("month_earned", 0) <= 0:
            continue
        rank += 1
        results.append((rank, doc, member))
    return results

# ── XP Pagination View ────────────────────────────────────────────────────────

EMOJI_WEEK  = "<:day7:1479248144112812124>"
EMOJI_MONTH = "<:day31:1479248528042754088>"

class XPLeaderboardView(discord.ui.View):
    def __init__(self, entries, guild, author_id, page=0, mode="all"):
        super().__init__(timeout=600)
        self.entries   = entries
        self.guild     = guild
        self.author_id = author_id
        self.page      = page
        self.mode      = mode  
        self.total_pages = max(1, -(-len(entries) // PAGE_SIZE))
        self.message: discord.Message | None = None
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()

    def _find_author(self):
        for rank, doc, member in self.entries:
            if doc.get("user_id") == self.author_id:
                return rank, doc
        return None, None

    def _update_buttons(self):
        self.prev_btn.disabled  = self.page == 0
        self.next_btn.disabled  = self.page >= self.total_pages - 1
        self.week_btn.style     = discord.ButtonStyle.primary if self.mode == "week"  else discord.ButtonStyle.secondary
        self.month_btn.style    = discord.ButtonStyle.primary if self.mode == "month" else discord.ButtonStyle.secondary
        self.alltime_btn.style  = discord.ButtonStyle.primary if self.mode == "all"   else discord.ButtonStyle.secondary

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try: await self.message.edit(view=self)
            except: pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Це не твоя команда.", ephemeral=True)
            return False
        return True

    def build(self):
        icon = self.guild.icon.url if self.guild.icon else None
        return build_xp_embed(self.entries, self.page, self.total_pages, icon, self.author_rank, self.author_data, self.mode)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:day7:1479248144112812124>"), style=discord.ButtonStyle.secondary, row=0)
    async def week_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_xp_week(self.guild)
        self.mode    = "week"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:day31:1479248528042754088>"), style=discord.ButtonStyle.secondary, row=0)
    async def month_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_xp_month(self.guild)
        self.mode    = "month"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:trophy:1475953207782932602>"), style=discord.ButtonStyle.primary, row=0)
    async def alltime_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_xp_leaderboard(self.guild)
        self.mode    = "all"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:vlivo:1475954870027681952>"), style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, _):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:vpravo:1475954959555235882>"), style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, _):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)

# ── Economy Pagination View ───────────────────────────────────────────────────

EMOJI_WEEK  = "<:day7:1479248144112812124>"
EMOJI_MONTH = "<:day31:1479248528042754088>"

class EcoLeaderboardView(discord.ui.View):
    def __init__(self, entries, guild, author_id, eco_settings, page=0, mode="all"):
        super().__init__(timeout=600)
        self.entries      = entries
        self.guild        = guild
        self.author_id    = author_id
        self.eco_settings = eco_settings
        self.page         = page
        self.mode         = mode  
        self.history_entries: list[dict] = []
        self.total_pages  = max(1, -(-len(entries) // PAGE_SIZE))
        self.message: discord.Message | None = None
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()

    def _find_author(self):
        for rank, doc, member in self.entries:
            if doc.get("user_id") == self.author_id:
                return rank, doc
        return None, None

    def _update_buttons(self):
        self.prev_btn.disabled  = self.page == 0
        self.next_btn.disabled  = self.page >= self.total_pages - 1
        self.week_btn.style     = discord.ButtonStyle.primary if self.mode == "week"  else discord.ButtonStyle.secondary
        self.month_btn.style    = discord.ButtonStyle.primary if self.mode == "month" else discord.ButtonStyle.secondary
        self.alltime_btn.style  = discord.ButtonStyle.primary if self.mode == "all"   else discord.ButtonStyle.secondary
        self.history_btn.style  = discord.ButtonStyle.primary if self.mode == "history" else discord.ButtonStyle.secondary

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try: await self.message.edit(view=self)
            except: pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Це не твоя команда.", ephemeral=True)
            return False
        return True

    def build(self):
        icon = self.guild.icon.url if self.guild.icon else None
        if self.mode == "history":
            return build_history_embed(self.history_entries, self.page, self.total_pages, icon, self.eco_settings, self.guild)

        return build_eco_embed(self.entries, self.page, self.total_pages, icon, self.author_rank, self.author_data, self.eco_settings, mode=self.mode)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:day7:1479248144112812124>"), style=discord.ButtonStyle.secondary, row=0)
    async def week_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_eco_week(self.guild)
        self.mode    = "week"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:day31:1479248528042754088>"), style=discord.ButtonStyle.secondary, row=0)
    async def month_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_eco_month(self.guild)
        self.mode    = "month"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:trophy:1475953207782932602>"), style=discord.ButtonStyle.primary, row=0)
    async def alltime_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_eco_leaderboard(self.guild)
        self.mode    = "all"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:historylist:1478824658332684510>"), style=discord.ButtonStyle.secondary, row=0)
    async def history_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        gd = await db.guild_settings.find_one({"_id": self.guild.id}) or {}
        history = gd.get("season_history", [])
        history_copy = list(history)
        history_copy.reverse()
        self.history_entries = history_copy
        self.mode = "history"
        self.page = 0
        self.total_pages = max(1, -(-len(self.history_entries) // PAGE_SIZE))
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:vlivo:1475954870027681952>"), style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, _):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:vpravo:1475954959555235882>"), style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, _):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)

# ── Cog з двома командами ─────────────────────────────────────────────────────

class LeaderboardCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Топ користувачів за рівнем XP")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        entries = await fetch_xp_leaderboard(interaction.guild)

        if not entries:
            await interaction.followup.send("<:inbox:1479128004847341620> На сервері ще немає статистики.", ephemeral=True)
            return

        view = XPLeaderboardView(entries, interaction.guild, interaction.user.id)
        msg  = await interaction.followup.send(embed=view.build(), view=view, wait=True)
        view.message = msg

    @app_commands.command(name="eco_top", description="Топ найбагатших гравців сервера")
    async def eco_top(self, interaction: discord.Interaction):
        await interaction.response.defer()
        entries  = await fetch_eco_leaderboard(interaction.guild)
        settings = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        eco_settings = settings.get("economy", {})

        if not entries:
            await interaction.followup.send("<:inbox:1479128004847341620> На сервері ще немає даних економіки.", ephemeral=True)
            return

        view = EcoLeaderboardView(entries, interaction.guild, interaction.user.id, eco_settings)
        msg  = await interaction.followup.send(embed=view.build(), view=view, wait=True)
        view.message = msg

async def setup(bot):
    await bot.add_cog(LeaderboardCommands(bot))
