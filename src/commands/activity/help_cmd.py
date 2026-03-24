"""
/help — головне меню допомоги бота.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config.constants import Emojis
from utils.ui_contract import add_section, set_surface_footer, surface_embed

E_HAMMER = Emojis.HAMMER.value
E_SETTING = Emojis.SETTINGS.value
E_STATS = Emojis.STATS.value
E_TICKET = Emojis.TICKET.value
E_HELP = Emojis.HELP.value
E_CHAT = Emojis.CHAT.value
E_COIN = Emojis.COIN.value
E_WARN = Emojis.WARN.value

SUPPORT_URL = "https://discord.gg/FJPkRjf5mA"
BOT_INVITE = "https://discord.com/oauth2/authorize?client_id=1396865832792887386&permissions=8&integration_type=0&scope=bot+applications.commands"

MODULES = {
    "moderation": {
        "emoji": E_HAMMER,
        "label": "Модерація",
        "desc": "Варни, тайм-аути, бани та історія покарань.",
        "commands": [
            ("`/warnings`", "Подивитися свої активні й минулі варни."),
            ("`/warn @user причина`", "Видати попередження."),
            ("`/warns @user`", "Переглянути історію варнів користувача."),
            ("`/mute @user час причина`", "Тимчасовий тайм-аут."),
            ("`/unmute @user`", "Зняти тайм-аут."),
            ("`/kick @user причина`", "Вигнати із сервера."),
            ("`/ban @user причина`", "Забанити назавжди."),
            ("`/purge`", "Очистити чат за обраним фільтром."),
        ],
    },
    "administration": {
        "emoji": E_SETTING,
        "label": "Адміністрування",
        "desc": "Головні панелі конфігу сервера та модулів.",
        "commands": [
            ("`/config`", "Єдиний центр керування модулями сервера."),
            ("`/automod`", "Панель автомодерації та custom rules."),
            ("`/economy_setup`", "Налаштування економіки, сезону, квестів і фонду."),
            ("`/warn-setup`", "Ескалації та спадання варнів."),
            ("`/logs`", "Лог-канали й події для аудиту."),
            ("`/welcome`", "Привітання, прощання та boost-картки."),
            ("`/settings`", "Level-up канал і обмеження команд."),
            ("`/autorole`", "Ролі для нових учасників."),
            ("`/colors`", "Панель кольорів нікнеймів."),
        ],
    },
    "activity": {
        "emoji": E_STATS,
        "label": "Активність",
        "desc": "Профілі, рейтинги, utility та voice-room системи.",
        "commands": [
            ("`/profile @user`", "Картка профілю з XP і економікою."),
            ("`/leaderboard`", "Топ активних учасників за XP."),
            ("`/economy_leaderboard`", "Топ гравців за економікою."),
            ("`/meme`", "Випадковий мем із Reddit."),
            ("`/avatar @user`", "Аватар у повному розмірі."),
            ("`/room-setup`", "Система приватних голосових кімнат."),
        ],
    },
    "tickets": {
        "emoji": E_TICKET,
        "label": "Тікети",
        "desc": "Підтримка, claim, close summary і transcript у лог-канал.",
        "commands": [
            ("`/ticket`", "Налаштування ticket-панелі, категорії, ролей і log channel."),
            ("`Claim / Close`", "Staff workflow усередині тікет-каналу."),
            ("`Transcript .txt`", "Автоматично летить у лог-канал під час закриття."),
            ("`/export`", "Клонування повідомлень між каналами."),
        ],
    },
    "economy": {
        "emoji": E_COIN,
        "label": "Економіка",
        "desc": "Гаманець, робота, злочини, квести, магазин і мініігри.",
        "commands": [
            ("`/economy`", "Гаманець, банк, переказ і пограбування."),
            ("`/daily`", "Щоденна нагорода та серія днів."),
            ("`/work`", "Легка або складна робота."),
            ("`/crime`", "Ризикована злочинна вилазка."),
            ("`/shop`", "Магазин ролей, бустів і предметів."),
            ("`/quests`", "Щоденні та тижневі квести."),
            ("`/slots` `/blackjack` `/coinflip`", "Казино та гемблінг."),
            ("`/roulette` `/highlow` `/duel @user`", "Додаткові ігри та дуелі."),
            ("`/faq`", "Детальний гайд по механіках економіки."),
        ],
    },
}

FEEDBACK = {
    "bug": {
        "emoji": E_HELP,
        "label": "Повідомити про баг",
        "desc": "Якщо щось зламалось або працює не так.",
        "text": (
            "Якщо побачили баг або дивну поведінку, скиньте кроки відтворення й очікуваний результат.\n\n"
            f"• [Сервер підтримки]({SUPPORT_URL})"
        ),
    },
    "question": {
        "emoji": E_CHAT,
        "label": "Поставити питання",
        "desc": "Якщо не ясно, де що налаштовується або як працює.",
        "text": (
            "Питання по командах, налаштуваннях або логіці бота краще ставити в підтримці.\n\n"
            f"• [Сервер підтримки]({SUPPORT_URL})"
        ),
    },
}


def _main_embed(user: discord.User, bot: discord.User) -> discord.Embed:
    embed = surface_embed(
        "navigation",
        title="Меню допомоги",
        description=(
            f"{user.mention}, це короткий центр навігації по **Vangard**.\n\n"
            "Спочатку оберіть модуль нижче. Якщо ви адміністратор і не знаєте, з чого почати, йдіть у `/config`."
        ),
    )
    embed.set_thumbnail(url=bot.display_avatar.url)
    add_section(
        embed,
        "Швидкий старт",
        [
            f"{E_SETTING} Адміну: почніть із `/config`, потім відкривайте профільні setup-панелі.",
            f"{E_WARN} Користувачу: `/warnings` показує ваші попередження.",
            f"{E_COIN} Для економіки головна точка входу — `/economy`.",
            f"{E_TICKET} Для підтримки та логів тікетів використовуйте `/ticket`.",
        ],
    )
    set_surface_footer(embed, "navigation", "Спочатку модуль, потім конкретна команда.")
    return embed


def _module_embed(key: str, bot: discord.User) -> discord.Embed:
    mod = MODULES[key]
    embed = surface_embed(
        "navigation",
        title=f"{mod['emoji']} {mod['label']}",
        description=mod["desc"],
    )
    embed.set_thumbnail(url=bot.display_avatar.url)
    add_section(embed, "Команди модуля", [f"{cmd} — {desc}" for cmd, desc in mod["commands"]])
    set_surface_footer(embed, "navigation", "Поверніться до списку модулів через селект вище.")
    return embed


def _feedback_embed(key: str, bot: discord.User, user: discord.User) -> discord.Embed:
    fb = FEEDBACK[key]
    embed = surface_embed(
        "navigation",
        title=f"{fb['emoji']} {fb['label']}",
        description=f"{user.mention}, {fb['text']}",
    )
    embed.set_thumbnail(url=bot.display_avatar.url)
    set_surface_footer(embed, "navigation", "Для багів додайте кроки відтворення і що саме очікували побачити.")
    return embed


class HelpView(discord.ui.View):
    def __init__(self, user: discord.User, bot_user: discord.User):
        super().__init__(timeout=180)
        self.user = user
        self.bot_user = bot_user
        self.add_item(ModuleSelect(bot_user))
        self.add_item(FeedbackSelect(user, bot_user))
        self.add_item(
            discord.ui.Button(
                label="Додати бота на сервер",
                style=discord.ButtonStyle.link,
                url=BOT_INVITE,
                row=2,
            )
        )


class ModuleSelect(discord.ui.Select):
    def __init__(self, bot_user: discord.User):
        self.bot_user = bot_user
        options = [
            discord.SelectOption(
                label=mod["label"],
                description=mod["desc"][:100],
                value=key,
                emoji=discord.PartialEmoji.from_str(mod["emoji"]),
            )
            for key, mod in MODULES.items()
        ]
        super().__init__(placeholder="Обрати модуль", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=_module_embed(self.values[0], self.bot_user))


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
        super().__init__(placeholder="Зворотний зв'язок", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=_feedback_embed(self.values[0], self.bot_user, self.fb_user))


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
