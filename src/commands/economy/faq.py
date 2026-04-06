import discord
from discord import app_commands
from discord.ext import commands
from config.constants import Emojis

COLOR = 0x1a1a2e
E_INFO = Emojis.INFO.value
E_COIN = Emojis.COIN.value
E_BANK = Emojis.BANK.value
E_WORK = Emojis.WORK.value
E_SHOP = Emojis.SHOP.value
E_BACKPACK = Emojis.BACKPACK.value
E_SHIELD = Emojis.SHIELD.value
E_STAR = Emojis.STAR.value
E_GIFT = Emojis.GIFT.value
E_LOOTBOX = Emojis.LOOTBOX.value
E_CLOCK = Emojis.CLOCK.value
E_LIST = Emojis.HISTORY.value
E_TROPHY = Emojis.TROPHY.value
E_MASK = Emojis.MASK.value
E_ROLE = Emojis.ROLE.value
E_EVENT = Emojis.EVENT.value

FAQ_DATA = {
    "economy": {
        "title": f"{E_COIN} Economy",
        "desc": (
            "`/wallet` — головна команда для гаманця, банку, переказів, інвентарю та історії дій.\n\n"
            "**Що тут є:**\n"
            "• гаманець і банк\n"
            "• перекази між гравцями\n"
            "• інвентар з предметами\n"
            "• історія транзакцій\n\n"
            "**З чого почати:**\n"
            "Використовуйте `/daily`, `/work` і активність у чаті, щоб отримати перші монети.\n\n"
            "**Де це налаштовується:**\n"
            "Економічні модулі, сезон, квести, аукціон і фонд керуються через `/economy_setup`."
        )
    },
    "crime_work_games": {
        "title": f"{E_WORK} Crime / Work / Games",
        "desc": (
            "`/work` дає стабільний заробіток через легкий або складний режим.\n"
            "`/crime` відкриває два сценарії: операцію або пограбування іншого гравця.\n\n"
            "**Що важливо знати:**\n"
            "• у `/crime` провал може дати штраф або crime ban\n"
            "• пограбування вибирає ціль через user select\n"
            "• `/slots`, `/roulette`, `/coinflip`, `/blackjack`, `/highlow` і `/duel` — це окремі ігрові поверхні\n\n"
            "**Де це налаштовується:**\n"
            "Ліміти, crime ban, gambling і ставки змінюються через `/economy_setup`."
        )
    },
    "xp_levels": {
        "title": f"{E_EVENT} XP / Levels",
        "desc": (
            "`/xp_setup` — головна панель для XP, level-up і ролей-нагород.\n\n"
            "**Що там налаштовується:**\n"
            "• XP за повідомлення, реакції та хвилину у voice\n"
            "• канал для level-up повідомлень\n"
            "• тумблер `Пінг` — чи згадувати користувача в level-up\n"
            "• тумблер `Opt-out` — чи може користувач вимкнути для себе такі сповіщення\n"
            "• правила `рівень -> роль`\n\n"
            "**Режими ролей-нагород:**\n"
            "• `highest_only` — залишається тільки найвища досягнута tracked role\n"
            "• `stack_all` — залишаються всі досягнуті tracked roles\n\n"
            "Після зміни правил використовуйте синхронізацію ролей у самому `/xp_setup`."
        )
    },
    "tickets": {
        "title": f"{E_ROLE} Tickets",
        "desc": (
            "`/ticket_setup` публікує панель створення тікетів і задає категорію, staff roles, лог-канал та transcript format.\n\n"
            "**Як це працює:**\n"
            "• користувач натискає кнопку на панелі\n"
            "• бот створює окремий тікет-канал\n"
            "• staff бере тікет через `Claim`\n"
            "• закриття через `Close` просить причину й відправляє `close summary` та `transcript` у `txt`, `html` або `txt + html`\n\n"
            "**Що важливо знати:**\n"
            "Нові налаштування застосовуються до нових тікетів і нової панелі, а не до старих повідомлень заднім числом."
        )
    },
    "moderation": {
        "title": f"{Emojis.HAMMER.value} Moderation",
        "desc": (
            "`/warn`, `/warnings`, `/warns` і `/unwarn` працюють як основа warning lifecycle.\n\n"
            "**Основний потік:**\n"
            "• `/warn` видає попередження\n"
            "• `/warnings` показує ваші active warns\n"
            "• `/warns @user` показує історію модерації користувача\n"
            "• `/unwarn` знімає warning без видалення кейсу\n\n"
            "**Де це налаштовується:**\n"
            "`/warn-setup` керує ескалаціями і спаданням попереджень.\n"
            "`/automod` відповідає за автомодерацію і custom rules."
        )
    },
    "voice_rooms": {
        "title": f"{E_BANK} Voice Rooms",
        "desc": (
            "`/room-setup` вмикає систему приватних voice-room каналів.\n\n"
            "**Що відбувається далі:**\n"
            "• користувач заходить у creator room\n"
            "• бот створює окрему приватну кімнату\n"
            "• панель керування дозволяє змінити назву, ліміт, доступ, власника і показати info card\n\n"
            "**Що важливо знати:**\n"
            "Кнопка `Інфо` показує поточний стан кімнати, а `Оновити` в цій картці перечитує його після змін."
        )
    }
}

class FaqSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Economy", description="wallet, банк, shop і базова економіка", value="economy", emoji=discord.PartialEmoji.from_str(E_COIN)),
            discord.SelectOption(label="Crime / Work / Games", description="робота, крайм, гемблінг і дуелі", value="crime_work_games", emoji=discord.PartialEmoji.from_str(E_WORK)),
            discord.SelectOption(label="XP / Levels", description="xp_setup, level-up і ролі-нагороди", value="xp_levels", emoji=discord.PartialEmoji.from_str(E_EVENT)),
            discord.SelectOption(label="Tickets", description="ticket_setup, claim, close, transcript", value="tickets", emoji=discord.PartialEmoji.from_str(E_ROLE)),
            discord.SelectOption(label="Moderation", description="warn, warnings, warns, unwarn", value="moderation", emoji=discord.PartialEmoji.from_str(Emojis.HAMMER.value)),
            discord.SelectOption(label="Voice Rooms", description="room-setup і приватні voice-room канали", value="voice_rooms", emoji=discord.PartialEmoji.from_str(E_BANK)),
        ]
        super().__init__(placeholder="Виберіть розділ для навчання...", options=options)

    async def callback(self, interaction: discord.Interaction):
        cat_id = self.values[0]
        data = FAQ_DATA.get(cat_id)
        if not data:
            return await interaction.response.send_message("Помилка розділу.", ephemeral=True)
            
        embed = discord.Embed(
            title=f"{E_INFO} Навчання | {data['title']}",
            description=data['desc'],
            color=COLOR
        )
        await interaction.response.edit_message(embed=embed)

class FaqView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(FaqSelect())

class FaqCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="faq", description="Короткий guide по системах бота та ключових механіках")
    async def faq_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"{E_INFO} Навчання та FAQ по боту",
            description=(
                "Тут зібрані короткі пояснення по основних системах бота.\n\n"
                "У селекті нижче є Economy, XP / Levels, Tickets, Moderation і Voice Rooms. "
                "Кожен розділ коротко пояснює, де це налаштовується, як цим користуватись і що важливо знати."
            ),
            color=COLOR
        )
        if interaction.guild and interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
            
        await interaction.response.send_message(embed=embed, view=FaqView(), ephemeral=True)

async def setup(bot):
    await bot.add_cog(FaqCommand(bot))
