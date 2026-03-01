"""
automod_engine.py
Мовчазний Автомод V13. Слухає повідомлення та оновлення профілів.
Застосовує правила з БД: антиспам, антилінки, антикапс, кастомні теги.
"""
import re
import discord
from discord.ext import commands
from collections import defaultdict, deque
import time
from services.automod import get_automod_config, normalize_string
from services.moderation import apply_case

# Anti-spam temporary tracking { user_id: deque([timestamp1, timestamp2, ...]) }
_SPAM_CACHE = defaultdict(lambda: deque(maxlen=5))

class AutomodEngine(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_whitelisted(self, message: discord.Message, config: dict) -> bool:
        if message.author.bot:
            return True
        if message.author.guild_permissions.manage_messages:
            return True
        
        # Check channel whitelist
        wl_channels = config.get("am_whitelist_channels", [])
        if message.channel.id in wl_channels:
            return True
        
        # Check role whitelist
        wl_roles = config.get("am_whitelist_roles", [])
        if any(role.id in wl_roles for role in message.author.roles):
            return True
            
        return False

    def _check_antispam(self, author_id: int) -> bool:
        """Returns True if the user is spamming (5 msgs in 5 secs)."""
        now = time.time()
        record = _SPAM_CACHE[author_id]
        record.append(now)
        if len(record) == 5:
            # Check elapsed time between 1st and 5th message
            if (record[-1] - record[0]) <= 5.0:
                record.clear() # Clear to prevent continuous triggers for the same burst
                return True
        return False

    async def _punish(self, message: discord.Message, reason: str, action: str = "warn"):
        try:
            await message.delete()
        except discord.NotFound:
            pass # Already deleted
        except discord.Forbidden:
            return # Missing perms to delete
        
        # Застосування покарання (відправляємо в БД Cases, що відобразиться на сайті)
        await apply_case(
            bot=self.bot,
            guild=message.guild,
            user=message.author,
            moderator=self.bot.user,
            action=action,
            reason=f"[Automod] {reason}"
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        config = get_automod_config(message.guild.id)
        if not config:
            return

        # Check whitelists
        if self._is_whitelisted(message, config):
            return

        content = message.content

        # 1. Anti-Spam
        if config.get("am_antispam", False):
            if self._check_antispam(message.author.id):
                return await self._punish(message, "Спам повідомленнями (Anti-Spam).")

        # 2. Anti-Invite
        if config.get("am_antiinvite", False):
            if "discord.gg/" in content.lower() or "discord.com/invite/" in content.lower():
                return await self._punish(message, "Надсилання Discord-запрошень заборонено.")

        # 3. Anti-Link
        if config.get("am_antilink", False):
            # Якщо анти-інвайт міг не спрацювати (або вимкнений), блокуємо ВСІ посилання
            # Використовуємо простий пошук URL
            url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
            if url_pattern.search(content):
                return await self._punish(message, "Надсилання посилань заборонено.")

        # 4. CAPSLOCK SPAM
        if config.get("am_caps", False) and len(content) > 10:
            uppers = sum(1 for c in content if c.isupper())
            if (uppers / len(content)) > 0.7:
                return await self._punish(message, "Використання надмірної кількості ВЕЛИКИХ ЛІТЕР.")

        # 5. Mass Mentions
        if config.get("am_mentions", False):
            if len(message.mentions) > 5:
                return await self._punish(message, "Надмірні згадки користувачів (Mass Mention).")

        # 6. Custom Trigger Rules (Automod Rules)
        rules = config.get("automod_rules", [])
        if rules:
            normalized_text = normalize_string(content)
            for rule in rules:
                normalized_rule = normalize_string(rule["trigger"])
                if normalized_rule and normalized_rule in normalized_text:
                    reason = rule.get("reason", "Заборонене слово/фраза.")
                    action = rule.get("action", "warn")
                    return await self._punish(message, f"Заборонений тег/фраза: {rule['trigger']} ({reason})", action)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return
            
        # Якщо профіль змінюється (ніки, ролі), перевіряємо кастомні теги
        # Це залишок від V12 для блокування кланових тегів у ніках
        if before.display_name == after.display_name and \
           before.global_name == after.global_name and \
           str(before.activities) == str(after.activities):
            return

        config = get_automod_config(after.guild.id)
        if not config: return
        
        rules = config.get("automod_rules", [])
        if not rules: return

        text_to_check = f"{after.display_name} {after.global_name or ''} "
        for activity in after.activities:
            if hasattr(activity, 'name') and activity.name: text_to_check += f"{activity.name} "
            if hasattr(activity, 'state') and activity.state: text_to_check += f"{activity.state} "

        normalized_text = normalize_string(text_to_check)
        for rule in rules:
            normalized_rule = normalize_string(rule["trigger"])
            if normalized_rule and normalized_rule in normalized_text:
                action = rule.get("action", "warn")
                reason = f"Заборонений тег в профілі/статусі: {rule['trigger']} ({rule.get('reason','')})"
                await apply_case(
                    bot=self.bot,
                    guild=after.guild,
                    user=after,
                    moderator=self.bot.user,
                    action=action,
                    reason=f"[Automod] {reason}"
                )
                return

async def setup(bot: commands.Bot):
    await bot.add_cog(AutomodEngine(bot))
