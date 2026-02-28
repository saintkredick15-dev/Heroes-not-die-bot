"""
automod_listener.py
Прослуховує івенти і пропускає учасників через Automod Cache.
"""
import discord
from discord.ext import commands
from services.automod import check_member_tags
from services.moderation import apply_case

class AutomodListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _process_member(self, member: discord.Member):
        if member.bot:
            return

        rule = check_member_tags(member.guild.id, member)
        if not rule:
            return

        # Якщо є порушення — генеруємо Case
        action = rule.get("action", "warn")
        reason = f"[Automod] Заборонений тег/фраза: {rule.get('trigger')} ({rule.get('reason', '')})"
        
        await apply_case(
            bot=self.bot,
            guild=member.guild,
            user=member,
            moderator=self.bot.user,
            action=action,
            reason=reason
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._process_member(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Якщо нічого пов'язаного із текстом не змінилось — ігноруємо
        if before.display_name == after.display_name and \
           before.global_name == after.global_name and \
           str(before.activities) == str(after.activities):
            return
        
        await self._process_member(after)

async def setup(bot: commands.Bot):
    await bot.add_cog(AutomodListener(bot))
