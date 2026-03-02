"""
automod_engine.py
Automod V2 Engine. Слухає повідомлення та застосовує правила з конфігу.
Читає ВСІ параметри з кешу (пороги, дії, тривалості, whitelists).
"""
import re
import hashlib
import discord
from discord.ext import commands
from collections import defaultdict, deque
import time
from services.automod import get_automod_config, normalize_string
from services.moderation import apply_case

# ── In-memory tracking ────────────────────────────────────────────────────────

# Flood: { user_id: deque([timestamp, ...]) }
_FLOOD_CACHE: dict[int, deque] = defaultdict(lambda: deque(maxlen=20))

# Duplicate: { user_id: deque([msg_hash, ...]) }
_DUP_CACHE: dict[int, deque] = defaultdict(lambda: deque(maxlen=10))

# Image/attachment spam: { user_id: deque([timestamp, ...]) }
_ATTACH_CACHE: dict[int, deque] = defaultdict(lambda: deque(maxlen=20))

# Cooldown: { user_id: float(timestamp) } — після покарання не рахуємо 10 секунд
_COOLDOWN: dict[int, float] = {}

# URL patterns
_URL_RE = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE)
_INVITE_RE = re.compile(
    r'(?:discord\.gg|discord\.com/invite|discordapp\.com/invite|dsc\.gg|discord\.io|invite\.gg)/([a-zA-Z0-9\-]+)',
    re.IGNORECASE
)

# Discord custom emoji pattern (to strip from caps analysis)
_EMOJI_RE = re.compile(r'<a?:\w+:\d+>')

# Emoji counting patterns
_CUSTOM_EMOJI_COUNT_RE = re.compile(r'<a?:\w+:\d+>')
_UNICODE_EMOJI_RE = re.compile(
    '[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
    '\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF'
    '\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF]+')

# Code block pattern (for caps analysis)
_CODE_BLOCK_RE = re.compile(r'```[\s\S]*?```|`[^`]+`')

# Duration parser for mute
_DUR_UNITS = {"m": 60, "h": 3600, "d": 86400}

def _parse_mute_seconds(raw: str) -> int:
    """Парсить '10m', '1h', '1d' у секунди. За замовч. 1 годину."""
    if not raw:
        return 3600
    raw = raw.strip().lower()
    match = re.match(r'^(\d+)\s*([mhd])$', raw)
    if not match:
        return 3600
    return int(match.group(1)) * _DUR_UNITS.get(match.group(2), 3600)


class AutomodEngine(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_whitelisted(self, message: discord.Message, config: dict) -> bool:
        if message.author.bot:
            return True
        if message.author.guild_permissions.administrator:
            return True
        if message.author.guild_permissions.manage_messages:
            return True
        wl_channels = config.get("am_whitelist_channels", [])
        if message.channel.id in wl_channels:
            return True
        wl_roles = config.get("am_whitelist_roles", [])
        if any(role.id in wl_roles for role in message.author.roles):
            return True
        return False

    def _in_cooldown(self, user_id: int) -> bool:
        ts = _COOLDOWN.get(user_id)
        if ts and (time.time() - ts) < 10:
            return True
        return False

    def _set_cooldown(self, user_id: int):
        _COOLDOWN[user_id] = time.time()

    # ── Checks ────────────────────────────────────────────────────────────────

    def _check_flood(self, author_id: int, count: int, interval: int) -> bool:
        now = time.time()
        record = _FLOOD_CACHE[author_id]
        record.append(now)
        if len(record) >= count:
            window = list(record)[-count:]
            if (window[-1] - window[0]) <= float(interval):
                record.clear()
                return True
        return False

    def _check_duplicate(self, author_id: int, text: str) -> bool:
        if not text.strip():
            return False
        h = hashlib.md5(text.lower().strip().encode()).hexdigest()
        record = _DUP_CACHE[author_id]
        record.append(h)
        # Якщо останні 3 повідомлення однакові
        recent = list(record)[-3:]
        if len(recent) == 3 and len(set(recent)) == 1:
            record.clear()
            return True
        return False

    async def _check_invite(self, content: str, allowed_servers: list, own_guild_id: int) -> bool:
        match = _INVITE_RE.search(content)
        if not match:
            return False

        code = match.group(1)

        # Витягуємо дозволені guild_id
        allowed_ids = {own_guild_id}  # Свій сервер завжди дозволено
        for s in allowed_servers:
            if isinstance(s, dict):
                allowed_ids.add(s.get("guild_id"))
            elif isinstance(s, (int, float)):
                allowed_ids.add(int(s))

        # Резолвимо invite через API
        try:
            invite = await self.bot.fetch_invite(code)
            if invite.guild and invite.guild.id in allowed_ids:
                return False  # Дозволений сервер
        except (discord.NotFound, discord.HTTPException):
            pass  # Невалідний/прострочений invite — блокуємо

        return True

    def _check_links(self, content: str, allowed_domains: list) -> bool:
        urls = _URL_RE.findall(content)
        if not urls:
            return False
        allowed_lower = [d.lower().strip() for d in allowed_domains if d.strip()]
        # Завжди дозволяємо Discord CDN
        allowed_lower.extend(["cdn.discordapp.com", "media.discordapp.net"])
        for url in urls:
            domain = re.sub(r'https?://', '', url).split('/')[0].lower()
            domain = domain.lstrip("www.")
            # Subdomain match: m.youtube.com -> youtube.com
            if not any(domain == a or domain.endswith("." + a) for a in allowed_lower):
                return True  # Заблокований URL знайдено
        return False

    def _check_caps(self, content: str, percent: int, minlen: int) -> bool:
        # Видаляємо code blocks, custom emoji та посилання
        clean = _CODE_BLOCK_RE.sub('', content)
        clean = _EMOJI_RE.sub('', clean)
        clean = _URL_RE.sub('', clean)
        # Залишаємо лише літери
        letters = [c for c in clean if c.isalpha()]
        if len(letters) < minlen:
            return False
        uppers = sum(1 for c in letters if c.isupper())
        ratio = uppers / len(letters) * 100
        return ratio >= percent

    def _check_emojis(self, content: str, max_emojis: int) -> bool:
        custom = len(_CUSTOM_EMOJI_COUNT_RE.findall(content))
        unicode_matches = _UNICODE_EMOJI_RE.findall(content)
        unicode_count = sum(len(m) for m in unicode_matches)
        return (custom + unicode_count) >= max_emojis

    def _check_image_spam(self, author_id: int, attachment_count: int,
                          max_count: int, interval: int) -> bool:
        if attachment_count == 0:
            return False
        now = time.time()
        record = _ATTACH_CACHE[author_id]
        for _ in range(attachment_count):
            record.append(now)
        if len(record) >= max_count:
            window = list(record)[-max_count:]
            if (window[-1] - window[0]) <= float(interval):
                record.clear()
                return True
        return False

    def _check_mentions(self, message: discord.Message, max_mentions: int) -> bool:
        count = len(message.mentions)
        if message.mention_everyone:
            count += 5
        count += len(message.role_mentions)
        return count >= max_mentions

    # ── Punish ────────────────────────────────────────────────────────────────

    async def _punish(self, message: discord.Message, reason: str,
                      action: str = "warn", mute_dur: str = ""):
        # Delete the message (завжди, для будь-якої комбінації)
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        self._set_cooldown(message.author.id)

        # Підтримка кількох дій через кому: "delete,warn", "mute,warn"
        actions = [a.strip().lower() for a in action.split(",")]

        for act in actions:
            if act == "delete":
                continue  # вже видалили зверху

            duration_hours = None
            if act == "mute":
                secs = _parse_mute_seconds(mute_dur)
                duration_hours = max(1, secs // 3600)

            await apply_case(
                bot=self.bot,
                guild=message.guild,
                user=message.author,
                moderator=self.bot.user,
                action=act,
                reason=f"[Automod] {reason}",
                duration_hours=duration_hours,
            )

    # ── Main listener ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        config = get_automod_config(message.guild.id)
        if not config:
            return

        if self._is_whitelisted(message, config):
            return

        if self._in_cooldown(message.author.id):
            return

        content = message.content

        # 1. Антиспам (флуд + дублікати)
        if config.get("am_antispam", False):
            count = config.get("am_antispam_count", 5)
            interval = config.get("am_antispam_interval", 5)
            action = config.get("am_antispam_action", "warn")
            mute_dur = config.get("am_antispam_mute_dur", "")

            if self._check_flood(message.author.id, count, interval):
                return await self._punish(message, "Флуд повідомленнями.", action, mute_dur)

            if config.get("am_antispam_duplicates", False):
                if self._check_duplicate(message.author.id, content):
                    return await self._punish(message, "Повторювані повідомлення.", action, mute_dur)

        # 2. Антизапрошення
        if config.get("am_antiinvite", False):
            allowed = config.get("am_antiinvite_allowed_servers", [])
            action = config.get("am_antiinvite_action", "delete")
            mute_dur = config.get("am_antiinvite_mute_dur", "")
            if await self._check_invite(content, allowed, message.guild.id):
                return await self._punish(message, "Discord-запрошення заборонені.", action, mute_dur)

        # 3. Анти-посилання
        if config.get("am_antilink", False):
            allowed = config.get("am_antilink_allowed_domains", [])
            action = config.get("am_antilink_action", "delete")
            mute_dur = config.get("am_antilink_mute_dur", "")
            if self._check_links(content, allowed):
                return await self._punish(message, "Посилання заборонені.", action, mute_dur)

        # 4. Анти-капс
        if config.get("am_caps", False):
            percent = config.get("am_caps_percent", 70)
            minlen = config.get("am_caps_minlen", 8)
            action = config.get("am_caps_action", "delete")
            mute_dur = config.get("am_caps_mute_dur", "")
            if self._check_caps(content, percent, minlen):
                return await self._punish(message, "Надмірне використання CAPS.", action, mute_dur)

        # 5. Анти-згадки
        if config.get("am_mentions", False):
            max_m = config.get("am_mentions_max", 5)
            action = config.get("am_mentions_action", "warn")
            mute_dur = config.get("am_mentions_mute_dur", "")
            if self._check_mentions(message, max_m):
                return await self._punish(message, "Масові згадки.", action, mute_dur)

        # 6. Emoji-спам
        if config.get("am_emojispam", False):
            max_e = config.get("am_emojispam_max", 10)
            action = config.get("am_emojispam_action", "delete")
            mute_dur = config.get("am_emojispam_mute_dur", "")
            if self._check_emojis(content, max_e):
                return await self._punish(message, "Надмірна кількість емодзі.", action, mute_dur)

        # 7. Image/Attachment-спам
        if config.get("am_imagespam", False):
            max_c = config.get("am_imagespam_count", 5)
            interval = config.get("am_imagespam_interval", 10)
            action = config.get("am_imagespam_action", "warn")
            mute_dur = config.get("am_imagespam_mute_dur", "")
            if self._check_image_spam(message.author.id, len(message.attachments), max_c, interval):
                return await self._punish(message, "Масове закидання файлів.", action, mute_dur)

        # 8. Заборонені слова/фрази
        rules = config.get("automod_rules", [])
        if rules:
            normalized_text = normalize_string(content)
            for rule in rules:
                normalized_rule = normalize_string(rule["trigger"])
                if normalized_rule and normalized_rule in normalized_text:
                    reason = rule.get("reason", "Заборонене слово.")
                    r_action = rule.get("action", "warn")
                    return await self._punish(
                        message, f"Заборонений тег: {rule['trigger']} ({reason})", r_action)

    # ── Member tag check ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return
        if (before.display_name == after.display_name and
                before.global_name == after.global_name and
                str(before.activities) == str(after.activities)):
            return

        config = get_automod_config(after.guild.id)
        if not config:
            return

        rules = config.get("automod_rules", [])
        if not rules:
            return

        text_to_check = f"{after.display_name} {after.global_name or ''} "
        for activity in after.activities:
            if hasattr(activity, 'name') and activity.name:
                text_to_check += f"{activity.name} "
            if hasattr(activity, 'state') and activity.state:
                text_to_check += f"{activity.state} "

        normalized_text = normalize_string(text_to_check)
        for rule in rules:
            normalized_rule = normalize_string(rule["trigger"])
            if normalized_rule and normalized_rule in normalized_text:
                action = rule.get("action", "warn")
                reason = f"Заборонений тег в профілі: {rule['trigger']}"
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
