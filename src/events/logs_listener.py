"""
logs_listener.py
Реальне логування Discord-івентів у канали, налаштовані через /logs.
Перевіряє білі списки перед логуванням.
"""
import discord
from discord.ext import commands
from datetime import datetime, timezone
from modules.db import get_database

db = get_database()

# ── Емодзі ────────────────────────────────────────────────────────────────────
E_SHIELD  = "<:shieldcheck:1477720160570839130>"
E_MEMBERS = "<:members:1477720603472691420>"
E_VOICE   = "<:supportrole:1476198036567756841>"
E_TRASH   = "<:trash:1477722148071145634>"
E_EDIT    = "<:edit:1476653567094820874>"
E_CROSS   = "<:krestik:1476693091355463842>"

EMBED_COLOR = 0x5865F2


async def _get_settings(guild_id: int) -> dict:
    return await db.guild_settings.find_one({"_id": guild_id}) or {}


def _is_whitelisted(settings: dict, channel_id: int = None, member: discord.Member = None) -> bool:
    """Перевіряє чи канал або роль учасника знаходиться у білому списку."""
    wl_channels = settings.get("log_whitelist_channels", [])
    if channel_id and channel_id in wl_channels:
        return True
    wl_roles = settings.get("log_whitelist_roles", [])
    if member and any(role.id in wl_roles for role in member.roles):
        return True
    return False


async def _send_log(guild: discord.Guild, settings: dict, log_key: str, embed: discord.Embed):
    """Відправляє embed у канал, прив'язаний до log_key."""
    ch_id = settings.get(log_key)
    if not ch_id:
        return
    channel = guild.get_channel(ch_id)
    if not channel:
        return
    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


class LogsListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Голосові канали ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        settings = await _get_settings(member.guild.id)
        if _is_whitelisted(settings, member=member):
            return

        now = datetime.now(timezone.utc)

        # Приєднався до голосового
        if before.channel is None and after.channel is not None:
            embed = discord.Embed(color=0x57F287, timestamp=now)
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.description = f"{E_VOICE} **{member.mention}** приєднався до {after.channel.mention}"
            await _send_log(member.guild, settings, "log_voice_join", embed)

        # Вийшов з голосового
        elif before.channel is not None and after.channel is None:
            embed = discord.Embed(color=0xED4245, timestamp=now)
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.description = f"{E_VOICE} **{member.mention}** відключився від {before.channel.mention}"
            await _send_log(member.guild, settings, "log_voice_leave", embed)

        # Переміщено між каналами
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            embed = discord.Embed(color=0xFEE75C, timestamp=now)
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.description = f"{E_VOICE} **{member.mention}** переміщено: {before.channel.mention} → {after.channel.mention}"
            await _send_log(member.guild, settings, "log_voice_move", embed)

    # ── Учасники ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        settings = await _get_settings(member.guild.id)
        if _is_whitelisted(settings, member=member):
            return

        embed = discord.Embed(color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.description = f"{E_MEMBERS} **{member.mention}** приєднався до сервера"
        embed.add_field(name="Акаунт створено", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        await _send_log(member.guild, settings, "log_member_join", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        settings = await _get_settings(member.guild.id)

        embed = discord.Embed(color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.description = f"{E_MEMBERS} **{member}** покинув сервер"
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        if roles:
            embed.add_field(name="Ролі", value=" ".join(roles[:10]), inline=False)
        await _send_log(member.guild, settings, "log_member_leave", embed)

    # ── Повідомлення ──────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        settings = await _get_settings(message.guild.id)
        if _is_whitelisted(settings, channel_id=message.channel.id, member=message.author):
            return

        embed = discord.Embed(color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        content = message.content[:1024] if message.content else "*порожнє*"
        embed.description = f"{E_TRASH} Повідомлення видалено в {message.channel.mention}"
        embed.add_field(name="Зміст", value=content, inline=False)
        await _send_log(message.guild, settings, "log_msg_delete", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return
        settings = await _get_settings(before.guild.id)
        if _is_whitelisted(settings, channel_id=before.channel.id, member=before.author):
            return

        embed = discord.Embed(color=0xFEE75C, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
        embed.description = f"{E_EDIT} Повідомлення відредаговано в {before.channel.mention}"
        embed.add_field(name="Було", value=before.content[:512] or "*порожнє*", inline=False)
        embed.add_field(name="Стало", value=after.content[:512] or "*порожнє*", inline=False)
        embed.add_field(name="Посилання", value=f"[Перейти]({after.jump_url})", inline=False)
        await _send_log(before.guild, settings, "log_msg_edit", embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LogsListener(bot))
