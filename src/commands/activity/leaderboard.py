from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from config.constants import Emojis
from modules.db import get_database
from repositories.user import get_level_xp
from utils.ui_contract import set_surface_footer, surface_embed

db = get_database()

# ── Кастомні емодзі ───────────────────────────────────────────────────────────
EMOJI_TROPHY = Emojis.TROPHY.value
EMOJI_MEDAL  = Emojis.MEDAL.value
EMOJI_CHAT   = Emojis.CHAT.value
EMOJI_MICRO  = Emojis.MICRO.value
EMOJI_STAR   = Emojis.STAR.value
EMOJI_NEXT   = Emojis.NEXT.value
EMOJI_PREV   = Emojis.PREV.value
EMOJI_COIN   = Emojis.COIN.value
EMOJI_BANK   = Emojis.BANK.value
EMOJI_STATS  = Emojis.STATS.value

RANK_BADGES = {1: EMOJI_TROPHY, 2: EMOJI_MEDAL, 3: EMOJI_STAR}
PAGE_SIZE   = 10


def _period_stat(doc: dict, field: str, mode: str) -> int:
    if mode == "week":
        return doc.get(f"{field}_week", 0)
    if mode == "month":
        return doc.get(f"{field}_month", 0)
    return doc.get(field, 0)

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
    cursor = db.users.find({"guild_id": guild.id}).sort("xp_week", -1).limit(200)
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
    cursor = db.users.find({"guild_id": guild.id}).sort("xp_month", -1).limit(200)
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
    embed = surface_embed("gameplay", "", None)
    mode_label = {"week": "7 DAYS", "month": "30 DAYS", "all": "ALL TIME"}.get(mode, "ALL TIME")
    embed.set_author(name=f"LEADERBOARD  -  XP  -  {mode_label}  -  {page + 1}/{total_pages}", icon_url=guild_icon)

    lines: list[str] = []
    for rank, doc, member in page_entries:
        level = doc.get("level", 1)
        xp = doc.get("xp", 0)
        needed = get_level_xp(level)
        badge = RANK_BADGES.get(rank, f"`{rank:>2}.`")
        name = member.display_name[:20]
        msgs = _period_stat(doc, "messages", mode)
        voice_h = round(_period_stat(doc, "voice_minutes", mode) / 60, 1)
        reactions = _period_stat(doc, "reactions", mode)

        if mode == "week":
            xp_period = doc.get("xp_week", 0)
            bar = make_xp_bar(xp_period, max(xp_period, needed, 1))
            lines.append(
                f"{badge} **{name}** - Lv.{level}\n"
                f"  `{bar}` +{xp_period} XP за 7 днів\n"
                f"  {EMOJI_CHAT} {msgs}  {EMOJI_MICRO} {voice_h}h  {EMOJI_STAR} {reactions}"
            )
        elif mode == "month":
            xp_period = doc.get("xp_month", 0)
            bar = make_xp_bar(xp_period, max(xp_period, needed, 1))
            lines.append(
                f"{badge} **{name}** - Lv.{level}\n"
                f"  `{bar}` +{xp_period} XP за 30 днів\n"
                f"  {EMOJI_CHAT} {msgs}  {EMOJI_MICRO} {voice_h}h  {EMOJI_STAR} {reactions}"
            )
        else:
            bar = make_xp_bar(xp, needed)
            lines.append(
                f"{badge} **{name}** - Lv.{level}\n"
                f"  `{bar}` {xp}/{needed} XP\n"
                f"  {EMOJI_CHAT} {msgs}  {EMOJI_MICRO} {voice_h}h  {EMOJI_STAR} {reactions}"
            )

    embed.description = "\n\n".join(lines) if lines else "*Поки що немає записів у цьому режимі.*"

    if author_rank and author_data:
        a_level = author_data.get("level", 1)
        if mode == "week":
            a_xp = author_data.get("xp_week", 0)
            footer_text = f"Ти #{author_rank} — рівень {a_level} — +{a_xp} XP за 7 днів"
        elif mode == "month":
            a_xp = author_data.get("xp_month", 0)
            footer_text = f"Ти #{author_rank} — рівень {a_level} — +{a_xp} XP за 30 днів"
        else:
            a_xp = author_data.get("xp", 0)
            a_needed = get_level_xp(a_level)
            footer_text = f"Ти #{author_rank} — рівень {a_level} — {a_xp}/{a_needed} XP"
        set_surface_footer(embed, "gameplay", footer_text)
    else:
        set_surface_footer(embed, "gameplay", f"Сторінка {page + 1}/{total_pages}")
    return embed

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
    embed = surface_embed("gameplay", "", None)

    title_mode = {"week": "7 DAYS", "month": "30 DAYS", "all": "ALL TIME"}.get(mode, "ALL TIME")
    embed.set_author(name=f"LEADERBOARD  -  ECONOMY  -  {title_mode}  -  {page + 1}/{total_pages}", icon_url=guild_icon)

    lines: list[str] = []
    for rank, doc, member in page_entries:
        badge = RANK_BADGES.get(rank, f"`{rank:>2}.`")
        name = member.display_name[:20]
        wallet = doc.get("wallet", 0)
        bank = doc.get("bank", 0)
        total = wallet + bank

        if mode == "week":
            earned = doc.get("week_earned", 0)
            line = f"{badge} **{name}** - `{earned:,}` {curr} in 7d"
            if wallet > 0 and bank > 0:
                line += f"\n  {EMOJI_COIN} `{wallet:,}`  {EMOJI_BANK} `{bank:,}`"
            else:
                line += f"\n  Total now: `{total:,}` {curr}"
            lines.append(line)
        elif mode == "month":
            earned = doc.get("month_earned", 0)
            line = f"{badge} **{name}** - `{earned:,}` {curr} in 30d"
            if wallet > 0 and bank > 0:
                line += f"\n  {EMOJI_COIN} `{wallet:,}`  {EMOJI_BANK} `{bank:,}`"
            else:
                line += f"\n  Total now: `{total:,}` {curr}"
            lines.append(line)
        else:
            line = f"{badge} **{name}** - `{total:,}` {curr}"
            if wallet > 0 and bank > 0:
                line += f"\n  {EMOJI_COIN} `{wallet:,}`  {EMOJI_BANK} `{bank:,}`"
            lines.append(line)

    embed.description = "\n\n".join(lines) if lines else "*Поки що немає економічних записів у цьому режимі.*"

    if author_rank and author_data:
        if mode == "week":
            a_val = author_data.get("week_earned", 0)
            footer_text = f"You are #{author_rank} - {a_val:,} {curr_name} in 7d"
        elif mode == "month":
            a_val = author_data.get("month_earned", 0)
            footer_text = f"Ти #{author_rank} — {a_val:,} {curr_name} за 30 днів"
        else:
            a_val = author_data.get("wallet", 0) + author_data.get("bank", 0)
            footer_text = f"Ти #{author_rank} — {a_val:,} {curr_name}"
        if mode == "week":
            footer_text = f"Ти #{author_rank} — {a_val:,} {curr_name} за 7 днів"
        set_surface_footer(embed, "gameplay", footer_text)
    else:
        set_surface_footer(embed, "gameplay", f"Сторінка {page + 1}/{total_pages}")
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
    embed = surface_embed("gameplay", "", None)
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

    embed.description = "\n".join(lines).strip() if lines else "*Історія сезонів поки що порожня.*"
    set_surface_footer(embed, "gameplay", f"Сторінка {page + 1}/{total_pages}")
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
        rank += 1
        results.append((rank, doc, member))
    return results

# ── XP Pagination View ────────────────────────────────────────────────────────

EMOJI_WEEK  = Emojis.DAY7.value
EMOJI_MONTH = Emojis.DAY31.value

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
            await interaction.response.send_message(f"{Emojis.CROSS.value} Це не твоя команда.", ephemeral=True)
            return False
        return True

    def build(self):
        icon = self.guild.icon.url if self.guild.icon else None
        return build_xp_embed(self.entries, self.page, self.total_pages, icon, self.author_rank, self.author_data, self.mode)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(Emojis.DAY7.value), style=discord.ButtonStyle.secondary, row=0)
    async def week_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_xp_week(self.guild)
        self.mode    = "week"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(Emojis.DAY31.value), style=discord.ButtonStyle.secondary, row=0)
    async def month_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_xp_month(self.guild)
        self.mode    = "month"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(Emojis.TROPHY.value), style=discord.ButtonStyle.primary, row=0)
    async def alltime_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_xp_leaderboard(self.guild)
        self.mode    = "all"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(Emojis.PREV.value), style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, _):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(Emojis.NEXT.value), style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, _):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)

# ── Economy Pagination View ───────────────────────────────────────────────────

EMOJI_WEEK  = Emojis.DAY7.value
EMOJI_MONTH = Emojis.DAY31.value

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
            await interaction.response.send_message(f"{Emojis.CROSS.value} Це не твоя команда.", ephemeral=True)
            return False
        return True

    def build(self):
        icon = self.guild.icon.url if self.guild.icon else None
        if self.mode == "history":
            return build_history_embed(self.history_entries, self.page, self.total_pages, icon, self.eco_settings, self.guild)

        return build_eco_embed(self.entries, self.page, self.total_pages, icon, self.author_rank, self.author_data, self.eco_settings, mode=self.mode)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(Emojis.DAY7.value), style=discord.ButtonStyle.secondary, row=0)
    async def week_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_eco_week(self.guild)
        self.mode    = "week"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(Emojis.DAY31.value), style=discord.ButtonStyle.secondary, row=0)
    async def month_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_eco_month(self.guild)
        self.mode    = "month"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:trophytop1:1485625873880191067>"), style=discord.ButtonStyle.primary, row=0)
    async def alltime_btn(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        self.entries = await fetch_eco_leaderboard(self.guild)
        self.mode    = "all"
        self.page    = 0
        self.total_pages = max(1, -(-len(self.entries) // PAGE_SIZE))
        self.author_rank, self.author_data = self._find_author()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:history:1485601911599009893>"), style=discord.ButtonStyle.secondary, row=0)
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

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(Emojis.PREV.value), style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, _):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str(Emojis.NEXT.value), style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, _):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build(), view=self)

# ── Cog з двома командами ─────────────────────────────────────────────────────

class LeaderboardCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _send_economy_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        entries = await fetch_eco_leaderboard(interaction.guild)
        settings = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        eco_settings = settings.get("economy", {})

        if not entries:
            await interaction.followup.send("<:inbox:1485599203815325836> No economy data yet.", ephemeral=True)
            return

        view = EcoLeaderboardView(entries, interaction.guild, interaction.user.id, eco_settings)
        msg = await interaction.followup.send(embed=view.build(), view=view, wait=True)
        view.message = msg

    @app_commands.command(name="leaderboard", description="XP leaderboard for this server")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        entries = await fetch_xp_leaderboard(interaction.guild)

        if not entries:
            await interaction.followup.send("<:inbox:1485599203815325836> No XP data yet.", ephemeral=True)
            return

        view = XPLeaderboardView(entries, interaction.guild, interaction.user.id)
        msg = await interaction.followup.send(embed=view.build(), view=view, wait=True)
        view.message = msg

    @app_commands.command(name="economy_leaderboard", description="Economy leaderboard for this server")
    async def economy_leaderboard(self, interaction: discord.Interaction):
        await self._send_economy_leaderboard(interaction)

async def setup(bot):
    await bot.add_cog(LeaderboardCommands(bot))
