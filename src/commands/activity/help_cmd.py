"""
/help — Меню допомоги бота Vangard.
Select з модулями + зворотній зв'язок + кнопка запрошення бота.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

E_HAMMER  = "<:hammer:1477376411642761479>"
E_SETTING = "<:settings:1476196821444591768>"
E_STATS   = "<:statistics:1477721796857041067>"
E_TICKET  = "<:supportrole:1476198036567756841>"
E_BUG     = "<:reasonqiestion:1476209697919860777>"
E_CHAT    = "<:chat:1475953787687403716>"

EMBED_COLOR = 0x1a1a2e
SUPPORT_URL = "https://discord.gg/FJPkRjf5mA"

BOT_INVITE  = "https://discord.com/oauth2/authorize?client_id=1396865832792887386&permissions=8&integration_type=0&scope=bot+applications.commands"

# ── Дані модулів ──────────────────────────────────────────────────────────────

MODULES = {
    "moderation": {
        "emoji": E_HAMMER,
        "label": "Модерація",
        "desc": "Команди для модерації сервера.",
        "commands": [
            ("`/warn @user причина`", "Видати попередження."),
            ("`/warns @user`", "Переглянути історію попереджень."),
            ("`/mute @user час причина`", "Тимчасовий тайм-аут."),
            ("`/unmute @user`", "Зняти тайм-аут."),
            ("`/kick @user причина`", "Вигнати з сервера."),
            ("`/ban @user причина`", "Забанити назавжди."),
            ("`/purge`", "Очистити чат за обраний період."),
        ],
    },
    "administration": {
        "emoji": E_SETTING,
        "label": "Адміністрування",
        "desc": "Налаштування сервера (тільки для адміністраторів).",
        "commands": [
            ("`/automod`", "Панель автомодерації (спам, лінки, капс)."),
            ("`/warn-setup`", "Ескалації та спадання варнів."),
            ("`/logs`", "Налаштування логування подій."),
            ("`/welcome`", "Привітання, прощання, бусти."),
            ("`/autorole`", "Авто-роль для нових учасників."),
            ("`/settings`", "Level-up канал та обмеження команд."),
            ("`/colors`", "Налаштування кольорів нікнеймів."),
        ],
    },
    "activity": {
        "emoji": E_STATS,
        "label": "Активність",
        "desc": "Профілі, рівні, меми та утиліти.",
        "commands": [
            ("`/profile @user`", "Картка профілю з XP та рівнем."),
            ("`/leaderboard`", "Топ активних учасників."),
            ("`/xp add/remove/set @user`", "Управління XP (адмін)."),
            ("`/meme`", "Випадковий мем з Reddit."),
            ("`/avatar @user`", "Аватар у повному розмірі."),
            ("`/room-setup`", "Приватні голосові кімнати."),
        ],
    },
    "tickets": {
        "emoji": E_TICKET,
        "label": "Тікети",
        "desc": "Система тікетів для підтримки.",
        "commands": [
            ("`/ticket`", "Налаштування тікет-системи."),
            ("`/export`", "Клонування повідомлень між каналами."),
        ],
    },
}

FEEDBACK = {
    "bug": {
        "emoji": E_BUG,
        "label": "Повідомити про баг",
        "desc": "Оповістіть нас про баг",
        "text": (
            "Ми будемо дуже **вдячні**, якщо ви повідомите про будь-які "
            "**баги** або **помилки** нашій підтримці.\n\n"
            "Ми стараємось для вас, але можемо допускати помилки, "
            "навіть після детального **тестування** нових функцій.\n\n"
            f"• [Сервер підтримки]({SUPPORT_URL})"
        ),
    },
    "question": {
        "emoji": E_CHAT,
        "label": "Задати питання",
        "desc": "Якщо у вас є питання",
        "text": (
            "Якщо у вас виникли **запитання**, ви можете поставити їх "
            "нашій службі підтримки. Ми з радістю допоможемо!\n\n"
            f"• [Сервер підтримки]({SUPPORT_URL})"
        ),
    },
}

def _main_embed(user: discord.User, bot: discord.User) -> discord.Embed:
    embed = discord.Embed(
        title="Меню допомоги",
        description=(
            f"{user.mention}, раді бачити вас у меню допомоги бота **Vangard**.\n\n"
            "Я — технологічний помічник для вашого сервера.\n"
            "**Оберіть** модуль знизу, або зверніться до підтримки.\n\n"
            "*Для деяких модулів потрібні права адміністратора.*"
        ),
        color=EMBED_COLOR,
    )
    embed.set_thumbnail(url=bot.display_avatar.url)
    embed.set_footer(text="Розробник: Kredick15")
    return embed

def _module_embed(key: str, bot: discord.User) -> discord.Embed:
    mod = MODULES[key]
    lines = [f"{cmd} — {desc}" for cmd, desc in mod["commands"]]
    embed = discord.Embed(
        title=f"{mod['emoji']} {mod['label']}",
        description=mod["desc"] + "\n\n" + "\n".join(lines),
        color=EMBED_COLOR,
    )
    embed.set_thumbnail(url=bot.display_avatar.url)
    embed.set_footer(text="Розробник: Kredick15")
    return embed

def _feedback_embed(key: str, bot: discord.User, user: discord.User) -> discord.Embed:
    fb = FEEDBACK[key]
    embed = discord.Embed(
        title=f"{fb['emoji']} {fb['label']}",
        description=f"{user.mention}, {fb['text']}",
        color=EMBED_COLOR,
    )
    embed.set_thumbnail(url=bot.display_avatar.url)
    embed.set_footer(text="Розробник: Kredick15")
    return embed

# ── View ──────────────────────────────────────────────────────────────────────

class HelpView(discord.ui.View):
    def __init__(self, user: discord.User, bot_user: discord.User):
        super().__init__(timeout=180)
        self.user = user
        self.bot_user = bot_user
        self.add_item(ModuleSelect(bot_user))
        self.add_item(FeedbackSelect(user, bot_user))
        self.add_item(discord.ui.Button(
            label="Додати бота на свій сервер",
            style=discord.ButtonStyle.link,
            url=BOT_INVITE,
            row=2,
        ))

class ModuleSelect(discord.ui.Select):
    def __init__(self, bot_user: discord.User):
        self.bot_user = bot_user
        options = [
            discord.SelectOption(
                label=mod["label"],
                description=mod["desc"][:50],
                value=key,
                emoji=discord.PartialEmoji.from_str(mod["emoji"]),
            )
            for key, mod in MODULES.items()
        ]
        super().__init__(placeholder="Обрати модуль", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        embed = _module_embed(self.values[0], self.bot_user)
        await interaction.response.edit_message(embed=embed)

class FeedbackSelect(discord.ui.Select):
    def __init__(self, user: discord.User, bot_user: discord.User):
        self.fb_user = user
        self.bot_user = bot_user
        options = [
            discord.SelectOption(
                label=fb["label"],
                description=fb["desc"],
                value=key,
                emoji=discord.PartialEmoji.from_str(fb["emoji"]),
            )
            for key, fb in FEEDBACK.items()
        ]
        super().__init__(placeholder="Зворотній зв'язок", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        embed = _feedback_embed(self.values[0], self.bot_user, self.fb_user)
        await interaction.response.edit_message(embed=embed)

# ── Cog ───────────────────────────────────────────────────────────────────────

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Меню допомоги бота Vangard")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = _main_embed(interaction.user, self.bot.user)
        view = HelpView(interaction.user, self.bot.user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
