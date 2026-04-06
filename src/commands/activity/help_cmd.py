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
        "desc": "Попередження, тайм-аути, бани та історія дій модерації.",
        "commands": [
            ("`/warnings`", "Подивитися свої попередження."),
            ("`/warn @user причина`", "Видати попередження."),
            ("`/warns @user`", "Переглянути історію попереджень користувача."),
            ("`/unwarn @user case_id`", "Зняти попередження без видалення кейсу."),
            ("`/mute @user час причина`", "Тимчасовий тайм-аут."),
            ("`/unmute @user`", "Зняти тайм-аут."),
            ("`/kick @user причина`", "Вигнати із сервера."),
            ("`/ban @user причина`", "Забанити назавжди."),
            ("`/purge`", "Очистити чат за вибраним фільтром."),
        ],
    },
    "administration": {
        "emoji": E_SETTING,
        "label": "Адміністрування",
        "desc": "Панелі налаштування сервера, XP, модерації та модулів.",
        "commands": [
            ("`/config`", "Огляд модулів сервера, пресети та імпорт/експорт."),
            ("`/automod`", "Панель автомодерації та custom rules."),
            ("`/economy_setup`", "Налаштування економіки, сезону, квестів та фонду."),
            ("`/xp_setup`", "XP ставки, level-up канал та ролі-нагороди."),
            ("`/warn-setup`", "Ескалації та спадання попереджень."),
            ("`/logs`", "Лог-канали та аудит-події."),
            ("`/welcome`", "Привітання, прощання та boost-картки."),
            ("`/settings`", "Обмеження користувацьких команд по каналах."),
            ("`/autorole`", "Ролі для нових учасників."),
            ("`/colors`", "Панель кольорів нікнеймів."),
        ],
    },
    "activity": {
        "emoji": E_STATS,
        "label": "Активність",
        "desc": "Профілі, рейтинги, utility та voice-room системи.",
        "commands": [
            ("`/profile @user`", "Картка профілю з XP та економікою."),
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
        "desc": "Панель підтримки, claim, close summary та transcript у txt/html.",
        "commands": [
            ("`/ticket_setup`", "Налаштування панелі, категорії, ролей, лог-каналу та transcript format."),
            ("`Claim / Close`", "Основні дії staff усередині тікет-каналу."),
            ("`Transcript txt/html`", "Під час закриття тікета летить у лог-канал у вибраному форматі."),
            ("`/export`", "Клонування повідомлень між каналами."),
        ],
    },
    "economy": {
        "emoji": E_COIN,
        "label": "Економіка",
        "desc": "Гаманець, робота, злочини, квести, магазин і мініігри.",
        "commands": [
            ("`/wallet`", "Гаманець, банк, переказ, інвентар та історія."),
            ("`/daily`", "Щоденна нагорода та серія днів."),
            ("`/work`", "Легка або складна робота."),
            ("`/crime`", "Операція або пограбування іншого гравця."),
            ("`/shop`", "Магазин ролей, бустів і предметів."),
            ("`/quests`", "Щоденні та тижневі квести."),
            ("`/slots` `/blackjack` `/coinflip`", "Казино та гемблінг."),
            ("`/roulette` `/highlow` `/duel @user`", "Додаткові ігри та дуелі."),
            ("`/faq`", "Гайд по механіках економіки."),
        ],
    },
}

FEEDBACK = {
    "bug": {
        "emoji": E_HELP,
        "label": "Повідомити про баг",
        "desc": "Якщо щось зламалось або працює не так.",
        "text": "Опишіть кроки відтворення та очікуваний результат у сервері підтримки.\n\n"
        f"• [Сервер підтримки]({SUPPORT_URL})",
    },
    "question": {
        "emoji": E_CHAT,
        "label": "Поставити питання",
        "desc": "Якщо неясно, де що налаштовується або як працює.",
        "text": "Питання по командах і налаштуваннях краще ставити в підтримці.\n\n"
        f"• [Сервер підтримки]({SUPPORT_URL})",
    },
}


def _main_embed(user: discord.User, bot_user: discord.User) -> discord.Embed:
    embed = surface_embed(
        "navigation",
        title="Меню допомоги",
        description=(
            f"{user.mention}, тут зібрані основні модулі й команди.\n\n"
            "Оберіть потрібний розділ у селекті нижче. Якщо ви налаштовуєте сервер з нуля, почніть із `/config`."
        ),
    )
    embed.set_thumbnail(url=bot_user.display_avatar.url)
    add_section(
        embed,
        "Швидкий старт",
        [
            f"{E_SETTING} Серверні модулі й пресети: `/config`.",
            f"{E_COIN} Гаманець, банк і перекази: `/wallet`.",
            f"{E_STATS} XP, level-up і ролі-нагороди: `/xp_setup`.",
            f"{E_TICKET} Панель тікетів і лог-канал: `/ticket_setup`.",
            f"{E_WARN} Попередження та історія модерації: `/warnings`, `/warns`, `/warn-setup`.",
        ],
    )
    set_surface_footer(embed, "navigation", "Оберіть модуль у селекті, щоб побачити ключові команди.")
    return embed


def _module_embed(key: str, bot_user: discord.User) -> discord.Embed:
    module = MODULES[key]
    embed = surface_embed("navigation", f"{module['emoji']} {module['label']}", module["desc"])
    embed.set_thumbnail(url=bot_user.display_avatar.url)
    add_section(embed, "Команди модуля", [f"{command} — {desc}" for command, desc in module["commands"]], inline=False)
    set_surface_footer(embed, "navigation", "Селект вище перемикає між модулями без повторного виклику /help.")
    return embed


def _feedback_embed(key: str, bot_user: discord.User, user: discord.User) -> discord.Embed:
    feedback = FEEDBACK[key]
    embed = surface_embed("navigation", f"{feedback['emoji']} {feedback['label']}", f"{user.mention}, {feedback['text']}")
    embed.set_thumbnail(url=bot_user.display_avatar.url)
    set_surface_footer(embed, "navigation", "Для багів додайте кроки відтворення, результат і сервер, де це сталося.")
    return embed


class ModuleSelect(discord.ui.Select):
    def __init__(self, bot_user: discord.User):
        self.bot_user = bot_user
        options = [
            discord.SelectOption(
                label=module["label"],
                description=module["desc"][:100],
                value=key,
                emoji=discord.PartialEmoji.from_str(module["emoji"]),
            )
            for key, module in MODULES.items()
        ]
        super().__init__(placeholder="Обрати модуль", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=_module_embed(self.values[0], self.bot_user))


class FeedbackSelect(discord.ui.Select):
    def __init__(self, user: discord.User, bot_user: discord.User):
        self.user = user
        self.bot_user = bot_user
        options = [
            discord.SelectOption(
                label=feedback["label"],
                description=feedback["desc"],
                value=key,
                emoji=discord.PartialEmoji.from_str(feedback["emoji"]),
            )
            for key, feedback in FEEDBACK.items()
        ]
        super().__init__(placeholder="Зворотний зв'язок", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=_feedback_embed(self.values[0], self.bot_user, self.user))


class HelpView(discord.ui.View):
    def __init__(self, user: discord.User, bot_user: discord.User):
        super().__init__(timeout=180)
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


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Коротка навігація по командах і модулях бота")
    async def help_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=_main_embed(interaction.user, self.bot.user),
            view=HelpView(interaction.user, self.bot.user),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
