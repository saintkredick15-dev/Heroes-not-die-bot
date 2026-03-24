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
    "basics": {
        "title": f"{E_COIN} Основи Економіки",
        "desc": (
            "Економіка на сервері дозволяє вам заробляти валюту, грати в ігри, торгувати та змагатися!\n\n"
            "**Основні команди:**\n"
            "• `/economy` — відкриває ваш головний гаманець. Тут ви можете класти кошти в банк, переказувати іншим та купувати предмети.\n"
            "• **Банк** — дозволяє зберігати кошти в безпеці. Гроші в банку недоступні для пограбування іншими гравцями, і на них може нараховуватись відсоток.\n"
            "• **Перекази** — діліться грошима з друзями (але за це може стягуватися комісія).\n\n"
            "**Як заробити перші гроші?**\n"
            "Виконуйте `/daily` щодня, отримуйте нагороду за повідомлення у чаті та використовуйте команду `/work`!"
        )
    },
    "jobs_crimes": {
        "title": f"{E_WORK} Роботи та Злочини",
        "desc": (
            "**Команда `/work` (Робота)**\n"
            "Є два види роботи: *Легка* та *Складна*.\n"
            "• **Легка:** Невелика стабільна зарплата + шанс зіграти у швидку міні-гру для додаткового бонусу.\n"
            "• **Складна:** Серія випробувань. Більше ризик, але значно більший куш наприкінці!\n\n"
            "**Команда `/crime` (Крайм)**\n"
            "Спробуйте зірвати великий куш! Але обережно: якщо вас спіймають, на вас буде накладено **Крайм Бан** (блок команди) та штраф.\n"
            "Якщо вас упіймали, є шанс дати **хабар**, щоб відкупитися.\n\n"
            "**Пограбування (/rob)**\n"
            "Використовуйте кнопку з `/economy`, щоб пограбувати іншого користувача за його ID. Вкрасти можна лише частину коштів з його гаманця (не банку)."
        )
    },
    "games": {
        "title": f"{Emojis.SLOTS_ALT.value} Ігри та Казино",
        "desc": (
            "Бажаєте подвоїти свій капітал? Спробуйте гемблінг!\n\n"
            "• `/slots` — Класичні слоти. Виб'єте 3 однакові емодзі — заберете великий множник!\n"
            "• `/roulette` — Ставки на червоне, чорне або зелене.\n"
            "• `/coinflip` — Ставка на Орел чи Решку.\n"
            "• `/blackjack` — Змагайтесь з дилером у 21.\n"
            "• `/highlow` — Вгадайте, чи наступне число буде вищим або нижчим.\n\n"
            "**Дуелі (/duel)**\n"
            "Кидайте виклик іншим гравцям на власні гроші! Обирайте дії в бою та перемагайте опонента, щоб забрати ставку."
        )
    },
    "shop": {
        "title": f"{E_SHOP} Магазин, Лутбокси та Інвентар",
        "desc": (
            "Витрачайте свої гроші з розумом у `/shop`!\n\n"
            "**Предмети:**\n"
            f"{E_SHIELD} **Щит** — повністю захищає від пограбувань на 24 години.\n"
            f"{E_STAR} **Coin Буст** — подвоює нагороди за активність у чаті.\n"
            "<:crimepass:1485614625025425529> **Crime Pass** — миттєво знімає заборону використання `/crime`.\n\n"
            "**Лутбокси:**\n"
            f"{E_LOOTBOX} Звичайні та {E_GIFT} Рідкісні лутбокси! Відкривайте їх через Інвентар для отримання грошей, предметів або унікальних ролей.\n\n"
            f"{E_BACKPACK} **Інвентар**\n"
            "Усі куплені предмети потрапляють до вашого Інвентарю (кнопка в `/economy`). Там ви можете активувати їх у потрібний момент!"
        )
    },
    "quests": {
        "title": "<:check:1485597845883981905> Квести",
        "desc": (
            "**Команда `/quests`**\n"
            "Щодня та щотижня ти отримуєш нові завдання: заробити певну суму, зіграти в казино, зробити пограбування тощо.\n\n"
            "Після виконання — натисни \"Забрати нагороду\" у панелі `/quests`.\n\n"
            "**Типи квестів:**\n"
            "• <:clock:1485618008784113796> **Денні** — скидаються кожні 24 години\n"
            "• <:star:1485626121847574631> **Тижневі** — скидаються кожен тиждень, більша нагорода"
        )
    },
    "season": {
        "title": "<:trophytop1:1485625873880191067> Сезони",
        "desc": (
            "**Що таке Сезон?**\n"
            "Сезон — це змагання між гравцями за монети. Хто накопичить найбільше до кінця сезону — отримує спеціальну роль.\n\n"
            "<:close:1485598320935174317> **За замовчуванням сезони вимкнені.** Адміністратор може увімкнути їх через `/economy_setup → Сезон`.\n\n"
            "**Що скидається в кінці сезону:**\n"
            "• <:coin:1485610808003133552> Монети (гаманець та банк — до нуля або стартового бонусу)\n"
            "• Архів результатів зберігається в `/economy_leaderboard → Архів сезонів`\n\n"
            "**Що НЕ скидається:** XP, рівень, хорошки в інвентарі.\n\n"
            "**Тривалість:** Зазвичай 30-90 днів."
        )
    },
    "vault": {
        "title": f"{E_BANK} Фонд Сервера та Аукціони",
        "desc": (
            "**Аукціон (/auction)**\n"
            "Спеціальний канал, де адміни виставляють цінні предмети або рідкісні кастомні ролі на торги. Хто поставить найбільше (переб'є ставку) до кінця таймеру — отримує лот!\n\n"
            "**Фонд Сервера (/fonds)**\n"
            "The Vault — спільна скринька серверу. Ми всі гуртом збираємо певну кількість валюти на глобальні цілі. Робіть пожертви та допомагайте досягти 100%!"
        )
    }
}

class FaqSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Про Економіку", description="Основи, баланс та банк", value="basics", emoji=discord.PartialEmoji.from_str(E_COIN)),
            discord.SelectOption(label="Роботи та Крайм", description="Легка/Складна робота, пограбування", value="jobs_crimes", emoji=discord.PartialEmoji.from_str(E_WORK)),
            discord.SelectOption(label="Ігри та Казино", description="Слоти, Дуелі, Блекджек...", value="games", emoji=discord.PartialEmoji.from_str(Emojis.SLOTS_ALT.value)),
            discord.SelectOption(label="Магазин та Інвентар", description="Предмети, Бусти, Лутбокси", value="shop", emoji=discord.PartialEmoji.from_str(E_SHOP)),
            discord.SelectOption(label="Квести", description="Денні та тижневі завдання", value="quests", emoji="<:check:1485597845883981905>"),
            discord.SelectOption(label="Сезони", description="Змагання та скидання монет", value="season", emoji="<:trophytop1:1485625873880191067>"),
            discord.SelectOption(label="Аукціон та Фонд", description="Загальний фонд сервера", value="vault", emoji="<:bank_safe:1485637217132216571>"),
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

    @app_commands.command(name="faq", description="Гайд по економіці, міні-іграм та системі бота")
    async def faq_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"{E_INFO} Навчання та FAQ по боту",
            description=(
                f"Вітаємо у довіднику!\n"
                f"Тут ви можете дізнатись як заробляти {E_COIN}, грати в ігри, працювати та багато іншого.\n\n"
                f"**Виберіть категорію в меню нижче**, щоб прочитати деталі."
            ),
            color=COLOR
        )
        if interaction.guild and interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
            
        await interaction.response.send_message(embed=embed, view=FaqView(), ephemeral=True)

async def setup(bot):
    await bot.add_cog(FaqCommand(bot))
