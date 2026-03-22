import random

import discord

from utils.ui_contract import gameplay_result_embed, set_surface_footer, surface_embed


def _result_embed(title: str, tone: str, description: str | None = None) -> discord.Embed:
    return gameplay_result_embed(title, description or "", tone=tone)


class BaseMinigame(discord.ui.View):
    def __init__(self, owner_id: int, stake: int, on_complete, timeout=15):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.stake = stake
        self.on_complete = on_complete
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Це не твоя гра!", ephemeral=True)
            return False
        return True

    async def finish(self, interaction: discord.Interaction, outcome: str, embed: discord.Embed):
        if self.finished:
            return
        self.finished = True
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        try:
            await self.on_complete(interaction, outcome, embed, self)
        except Exception:
            pass

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        try:
            await self.on_complete(
                None,
                "lose",
                _result_embed("⏰ Час вийшов", "error", "Ви нічого не обрали."),
                self,
            )
        except Exception:
            pass


class MathQuizView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        first = random.randint(10, 50)
        second = random.randint(10, 50)
        operator = random.choice(["+", "-"])
        self.answer = first + second if operator == "+" else first - second
        self.question = f"{first} {operator} {second} = ?"

        choices = [self.answer, self.answer + random.randint(1, 10), self.answer - random.randint(1, 10), self.answer + random.randint(-5, 5)]
        choices = list(set(choices))
        while len(choices) < 3:
            choices.append(self.answer + random.randint(10, 20))
            choices = list(set(choices))
        random.shuffle(choices)

        for choice in choices[:3]:
            button = discord.ui.Button(label=str(choice), style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(choice)
            self.add_item(button)

    def _make_callback(self, value: int):
        async def callback(interaction: discord.Interaction):
            if value == self.answer:
                embed = _result_embed("<:cutiecheckmark:1479120440734650389> Вірно!", "success", f"{self.question} {self.answer}")
                await self.finish(interaction, "win", embed)
            else:
                embed = _result_embed("<:cutiex:1480246146076119132> Помилка!", "error", f"Правильна відповідь: {self.answer}")
                await self.finish(interaction, "lose", embed)

        return callback


class HigherLowerView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        self.base_num = random.randint(20, 80)
        self.secret = random.randint(1, 100)
        while self.secret == self.base_num:
            self.secret = random.randint(1, 100)

    @discord.ui.button(label="Більше ⬆️", style=discord.ButtonStyle.success)
    async def btn_high(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._check(interaction, self.secret > self.base_num)

    @discord.ui.button(label="Менше ⬇️", style=discord.ButtonStyle.danger)
    async def btn_low(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._check(interaction, self.secret < self.base_num)

    async def _check(self, interaction: discord.Interaction, is_correct: bool):
        if is_correct:
            embed = _result_embed("<:cutiecheckmark:1479120440734650389> Вгадав!", "success", f"Наступне число було **{self.secret}**")
            await self.finish(interaction, "win", embed)
        else:
            embed = _result_embed("<:cutiex:1480246146076119132> Не вгадав!", "error", f"Наступне число було **{self.secret}**")
            await self.finish(interaction, "lose", embed)


class ShellGameView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        self.winning_idx = random.randint(0, 2)
        for index in range(3):
            button = discord.ui.Button(emoji="<:openlootbox:1479952212980535498>", style=discord.ButtonStyle.secondary)
            button.callback = self._make_callback(index)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            for item_index, child in enumerate(self.children):
                if item_index == self.winning_idx:
                    child.emoji = "💎"
                    child.style = discord.ButtonStyle.success
                else:
                    child.emoji = "<:cutiex:1480246146076119132>"
                    child.style = discord.ButtonStyle.danger

            if index == self.winning_idx:
                embed = _result_embed("<:cutiecheckmark:1479120440734650389> Відгадав!", "success", "Ти знайшов приз.")
                await self.finish(interaction, "win", embed)
            else:
                embed = _result_embed("<:cutiex:1480246146076119132> Пусто!", "error", "Ти не вгадав коробочку.")
                await self.finish(interaction, "lose", embed)

        return callback


class DiceDuelView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)

    @discord.ui.button(label="Кинути кубики 🎲", style=discord.ButtonStyle.primary)
    async def roll(self, interaction: discord.Interaction, _: discord.ui.Button):
        user_roll = random.randint(2, 12)
        bot_roll = random.randint(2, 12)

        if user_roll > bot_roll:
            embed = _result_embed("<:cutiecheckmark:1479120440734650389> Перемога!", "success", f"Твій кидок: **{user_roll}**\nКидок суперника: **{bot_roll}**")
            await self.finish(interaction, "win", embed)
        elif user_roll < bot_roll:
            embed = _result_embed("<:cutiex:1480246146076119132> Поразка!", "error", f"Твій кидок: **{user_roll}**\nКидок суперника: **{bot_roll}**")
            await self.finish(interaction, "lose", embed)
        else:
            embed = _result_embed("🤝 Нічия!", "warning", f"Обидва кинули **{user_roll}**")
            await self.finish(interaction, "draw", embed)


class OddEmojiView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=12)
        pairs = [("🍎", "🍅"), ("😀", "😃"), ("🦊", "🐺"), ("⚽", "🏀"), ("🚗", "🚜")]
        base_emoji, odd_emoji = random.choice(pairs)
        self.odd_idx = random.randint(0, 4)

        for index in range(5):
            emoji = odd_emoji if index == self.odd_idx else base_emoji
            button = discord.ui.Button(emoji=emoji, style=discord.ButtonStyle.secondary)
            button.callback = self._make_callback(index)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if index == self.odd_idx:
                await self.finish(interaction, "win", _result_embed("<:cutiecheckmark:1479120440734650389> Знайшов зайве!", "success"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:cutiex:1480246146076119132> Промах!", "error"))

        return callback


class UnscrambleView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        words = ["економіка", "циган", "монета", "капітал", "робота", "банк", "сейф", "податок"]
        self.word = random.choice(words)
        letters = list(self.word)
        random.shuffle(letters)
        while "".join(letters) == self.word:
            random.shuffle(letters)
        self.scrambled = "".join(letters).upper()

        choices = [self.word]
        while len(choices) < 4:
            choice = random.choice(words)
            if choice not in choices:
                choices.append(choice)
        random.shuffle(choices)

        for choice in choices:
            button = discord.ui.Button(label=choice.capitalize(), style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(choice)
            self.add_item(button)

    def _make_callback(self, choice: str):
        async def callback(interaction: discord.Interaction):
            if choice == self.word:
                await self.finish(interaction, "win", _result_embed("<:cutiecheckmark:1479120440734650389> Правильно!", "success", f"Слово було: **{self.word}**"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:cutiex:1480246146076119132> Помилка!", "error", f"Слово було: **{self.word}**"))

        return callback


class TriviaView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        questions = [
            ("Скільки днів у високосному році?", "366", ["365", "364", "367"]),
            ("Хто намалював Мону Лізу?", "Да Вінчі", ["Пікассо", "Ван Гог", "Далі"]),
            ("Скільки континентів на Землі?", "7", ["5", "6", "8"]),
            ("Як називається найдовша річка?", "Ніл", ["Амазонка", "Дніпро", "Міссісіпі"]),
            ("Що більше важить: кілограм вати чи цвяхів?", "Однаково", ["Цвяхи", "Вата", "Невідомо"]),
        ]
        self.question, answer, wrong = random.choice(questions)
        choices = wrong + [answer]
        random.shuffle(choices)

        for choice in choices:
            button = discord.ui.Button(label=choice, style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(choice == answer, answer)
            self.add_item(button)

    def _make_callback(self, correct: bool, answer: str):
        async def callback(interaction: discord.Interaction):
            if correct:
                await self.finish(interaction, "win", _result_embed("<:cutiecheckmark:1479120440734650389> Вірно!", "success", f"Відповідь: **{answer}**"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:cutiex:1480246146076119132> Невірно!", "error", f"Правильна: **{answer}**"))

        return callback


class TypingModal(discord.ui.Modal, title="Швидкий друк"):
    word_input = discord.ui.TextInput(label="Введіть слово", placeholder="...", required=True)

    def __init__(self, expected_word: str, finish_callback):
        super().__init__()
        self.expected_word = expected_word
        self.finish_callback = finish_callback

    async def on_submit(self, interaction: discord.Interaction):
        if self.word_input.value.strip().lower() == self.expected_word.lower():
            await self.finish_callback(interaction, "win", _result_embed("<:cutiecheckmark:1479120440734650389> Вірно надруковано!", "success"))
        else:
            await self.finish_callback(
                interaction,
                "lose",
                _result_embed("<:cutiex:1480246146076119132> Помилка в слові!", "error", f"Очікувалось: **{self.expected_word}**"),
            )


class TypingTestView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        self.word = random.choice(["інвестор", "криптовалюта", "дивіденди", "активи", "блокчейн"])
        self.desc = f"Надрукуй слово без помилок:\n\n# {self.word}"

    @discord.ui.button(label="Надрукувати ⌨️", style=discord.ButtonStyle.primary)
    async def btn_type(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(TypingModal(self.word, self.finish))


class GuessNumberView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=12)
        self.winner = random.randint(1, 5)
        for number in range(1, 6):
            button = discord.ui.Button(label=str(number), style=discord.ButtonStyle.secondary)
            button.callback = self._make_callback(number)
            self.add_item(button)

    def _make_callback(self, number: int):
        async def callback(interaction: discord.Interaction):
            for child in self.children:
                child.style = discord.ButtonStyle.success if int(child.label) == self.winner else discord.ButtonStyle.danger
            if number == self.winner:
                await self.finish(interaction, "win", _result_embed("<:cutiecheckmark:1479120440734650389> Вгадав число!", "success"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:cutiex:1480246146076119132> Не вгадав!", "error", f"Було число **{self.winner}**"))

        return callback


class ReactionTestView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=10)
        self.green_idx = random.randint(0, 3)
        for index in range(4):
            style = discord.ButtonStyle.success if index == self.green_idx else discord.ButtonStyle.secondary
            button = discord.ui.Button(label="ТИСНИ" if index == self.green_idx else "Ні", style=style)
            button.callback = self._make_callback(index)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if index == self.green_idx:
                await self.finish(interaction, "win", _result_embed("<:cutiecheckmark:1479120440734650389> Швидка реакція!", "success"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:cutiex:1480246146076119132> Натиснув не туди!", "error"))

        return callback


def get_random_minigame(owner_id: int, stake: int, eco: dict, on_complete) -> tuple[discord.Embed, discord.ui.View]:
    enabled_keys = eco.get(
        "enabled_minigames",
        ["math", "higher_lower", "shell", "dice", "odd_emoji", "unscramble", "trivia", "typing", "guess", "reaction"],
    )

    all_games = [
        {"id": "math", "class": MathQuizView, "title": "🧮 Математика", "desc": "Розв'яжи приклад за 15 секунд."},
        {"id": "higher_lower", "class": HigherLowerView, "title": "📈 Більше чи менше", "desc": "Наступне число буде вище чи нижче."},
        {"id": "shell", "class": ShellGameView, "title": "<:openlootbox:1479952212980535498> Наперстки", "desc": "Вгадай, де захований діамант."},
        {"id": "dice", "class": DiceDuelView, "title": "🎲 Кості", "desc": "Кинь кубики й спробуй переграти суперника."},
        {"id": "odd_emoji", "class": OddEmojiView, "title": "🔍 Зайвий емодзі", "desc": "Знайди зайвий емодзі серед інших за 12 секунд."},
        {"id": "unscramble", "class": UnscrambleView, "title": "🔤 Анаграмма", "desc": "Знайди правильне слово серед варіантів."},
        {"id": "trivia", "class": TriviaView, "title": "🧠 Вікторина", "desc": "Обери правильну відповідь на питання."},
        {"id": "typing", "class": TypingTestView, "title": "⌨️ Швидкий друк", "desc": "Надрукуй слово без помилок."},
        {"id": "guess", "class": GuessNumberView, "title": "🔢 Відгадай число", "desc": "Яке з чисел від 1 до 5 було загадане?"},
        {"id": "reaction", "class": ReactionTestView, "title": "⚡ Реакція", "desc": "Якнайшвидше натисни зелену кнопку."},
    ]

    games = [game for game in all_games if game["id"] in enabled_keys] or all_games
    selected = random.choice(games)
    view = selected["class"](owner_id, stake, on_complete)

    embed = surface_embed("gameplay", selected["title"], selected["desc"], tone="warning")
    if isinstance(view, HigherLowerView):
        embed.description += f"\n\nПоточне число: **{view.base_num}**"
    elif isinstance(view, MathQuizView):
        embed.description += f"\n\n**{view.question}**"
    elif isinstance(view, UnscrambleView):
        embed.description += f"\n\nСлово: **{view.scrambled}**"
    elif isinstance(view, TriviaView):
        embed.description += f"\n\n**{view.question}**"
    elif isinstance(view, TypingTestView):
        embed.description = view.desc
    set_surface_footer(embed, "gameplay", "Спершу прочитай умову, потім тисни кнопку або обирай відповідь.")
    return embed, view


async def setup(bot):
    pass
