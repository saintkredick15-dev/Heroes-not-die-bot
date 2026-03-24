import random
from dataclasses import dataclass

import discord

from utils.ui_contract import gameplay_result_embed, set_surface_footer, surface_embed


def _result_embed(title: str, tone: str, description: str | None = None) -> discord.Embed:
    return gameplay_result_embed(title, description or "", tone=tone)


MATH_TIMEOUTS = {
    "easy": 12,
    "medium": 20,
    "hard": 30,
}

MATH_REWARD_MULTIPLIERS = {
    "easy": 1.0,
    "medium": 1.25,
    "hard": 1.5,
}

MATH_PROFILE_WEIGHTS = {
    "default": (("easy", 60), ("medium", 30), ("hard", 10)),
    "simple_work": (("easy", 70), ("medium", 30)),
    "complex_work": (("easy", 20), ("medium", 55), ("hard", 25)),
    "crime": (("medium", 65), ("hard", 35)),
}

MATH_DIFFICULTY_LABELS = {
    "easy": "легка",
    "medium": "середня",
    "hard": "складна",
}


@dataclass(frozen=True)
class MathTask:
    question: str
    answer: int
    difficulty: str
    timeout: int
    reward_mult: float


def pick_math_difficulty(profile: str = "default", rng: random.Random | None = None) -> str:
    rng = rng or random
    weighted = MATH_PROFILE_WEIGHTS.get(profile, MATH_PROFILE_WEIGHTS["default"])
    names = [name for name, _ in weighted]
    weights = [weight for _, weight in weighted]
    return rng.choices(names, weights=weights, k=1)[0]


def _build_easy_math_task(rng: random.Random) -> tuple[str, int]:
    builders = [
        lambda: (
            lambda a, b: (f"{a} + {b} = ?", a + b)
        )(rng.randint(5, 60), rng.randint(5, 60)),
        lambda: (
            lambda a, b: (f"{a} - {b} = ?", a - b)
        )(*sorted((rng.randint(10, 80), rng.randint(5, 50)), reverse=True)),
        lambda: (
            lambda a, b: (f"{a} × {b} = ?", a * b)
        )(rng.randint(3, 12), rng.randint(4, 12)),
    ]
    return rng.choice(builders)()


def _build_medium_math_task(rng: random.Random) -> tuple[str, int]:
    def build_division_combo() -> tuple[str, int]:
        divisor = rng.choice([3, 4, 5, 6, 7, 8])
        answer = rng.randint(6, 18)
        extra = rng.choice([6, 8, 10, 12, 14, 16, 18, 20, 24, 28])
        left = answer * divisor - extra
        return f"({left} + {extra}) / {divisor} = ?", answer

    def build_percent() -> tuple[str, int]:
        percent, base = rng.choice(
            [
                (10, 320),
                (12, 250),
                (15, 240),
                (20, 180),
                (25, 88),
            ]
        )
        return f"{percent}% від {base} = ?", int(base * percent / 100)

    def build_decimal() -> tuple[str, int]:
        factor, base = rng.choice(
            [
                (1.5, 40),
                (2.5, 16),
                (1.5, 60),
                (2.5, 24),
                (0.5, 84),
            ]
        )
        factor_text = str(int(factor)) if float(factor).is_integer() else str(factor)
        return f"{factor_text} × {base} = ?", int(factor * base)

    builders = [
        lambda: (
            lambda a, b: (f"{a} × {b} = ?", a * b)
        )(rng.randint(11, 19), rng.randint(6, 9)),
        build_division_combo,
        build_percent,
        build_decimal,
    ]
    return rng.choice(builders)()


def _build_hard_math_task(rng: random.Random) -> tuple[str, int]:
    def build_large_multiply() -> tuple[str, int]:
        a, b = rng.choice([(35, 12), (48, 9), (27, 16), (42, 11), (36, 14)])
        return f"{a} × {b} = ?", a * b

    def build_square_gap() -> tuple[str, int]:
        left = rng.randint(18, 25)
        right = left - rng.choice([1, 2])
        return f"{left}² - {right}² = ?", left * left - right * right

    def build_root_combo() -> tuple[str, int]:
        square, delta = rng.choice([(144, 18), (196, -5), (169, 11), (225, -3)])
        return f"√{square} {'+' if delta >= 0 else '-'} {abs(delta)} = ?", int(square**0.5) + delta

    def build_scaled_division() -> tuple[str, int]:
        left, divisor, multiplier = rng.choice([(84, 7, 6), (96, 8, 7), (108, 9, 5), (144, 12, 4)])
        return f"({left} / {divisor}) × {multiplier} = ?", int(left / divisor) * multiplier

    def build_decimal() -> tuple[str, int]:
        factor, base = rng.choice([(1.5, 240), (2.5, 96), (3.5, 40)])
        factor_text = str(int(factor)) if float(factor).is_integer() else str(factor)
        return f"{factor_text} × {base} = ?", int(factor * base)

    builders = [
        build_large_multiply,
        build_square_gap,
        build_root_combo,
        build_scaled_division,
        build_decimal,
    ]
    return rng.choice(builders)()


def generate_math_task_for_difficulty(
    difficulty: str, rng: random.Random | None = None
) -> MathTask:
    rng = rng or random
    normalized = difficulty if difficulty in MATH_TIMEOUTS else "easy"
    builders = {
        "easy": _build_easy_math_task,
        "medium": _build_medium_math_task,
        "hard": _build_hard_math_task,
    }
    question, answer = builders[normalized](rng)
    return MathTask(
        question=question,
        answer=answer,
        difficulty=normalized,
        timeout=MATH_TIMEOUTS[normalized],
        reward_mult=MATH_REWARD_MULTIPLIERS[normalized],
    )


def generate_math_task(profile: str = "default", rng: random.Random | None = None) -> MathTask:
    rng = rng or random
    difficulty = pick_math_difficulty(profile, rng)
    return generate_math_task_for_difficulty(difficulty, rng)


class BaseMinigame(discord.ui.View):
    def __init__(self, owner_id: int, stake: int, on_complete, timeout=15):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.stake = stake
        self.on_complete = on_complete
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("<:close:1485598320935174317> Це не твоя гра!", ephemeral=True)
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
    def __init__(self, owner_id: int, stake: int, on_complete, profile: str = "default"):
        self.task = generate_math_task(profile)
        super().__init__(owner_id, stake, on_complete, timeout=self.task.timeout)
        self.answer = self.task.answer
        self.question = self.task.question
        self.difficulty = self.task.difficulty
        self.reward_mult = self.task.reward_mult
        self.desc = (
            f"Рівень: **{MATH_DIFFICULTY_LABELS[self.difficulty]}**\n"
            f"Час: **{self.task.timeout} с**"
        )

        choices = [self.answer]
        spread = {
            "easy": (2, 7),
            "medium": (4, 15),
            "hard": (8, 30),
        }[self.difficulty]
        while len(choices) < 4:
            delta = random.randint(spread[0], spread[1])
            candidate = self.answer + random.choice((-delta, delta))
            if candidate != self.answer:
                choices.append(candidate)
            choices = list(dict.fromkeys(choices))
        random.shuffle(choices)

        for choice in choices[:3]:
            button = discord.ui.Button(label=str(choice), style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(choice)
            self.add_item(button)

    def _make_callback(self, value: int):
        async def callback(interaction: discord.Interaction):
            if value == self.answer:
                embed = _result_embed("<:check:1485597845883981905> Вірно!", "success", f"{self.question} {self.answer}")
                await self.finish(interaction, "win", embed)
            else:
                embed = _result_embed("<:close:1485598320935174317> Помилка!", "error", f"Правильна відповідь: {self.answer}")
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
            embed = _result_embed("<:check:1485597845883981905> Вгадав!", "success", f"Наступне число було **{self.secret}**")
            await self.finish(interaction, "win", embed)
        else:
            embed = _result_embed("<:close:1485598320935174317> Не вгадав!", "error", f"Наступне число було **{self.secret}**")
            await self.finish(interaction, "lose", embed)


class ShellGameView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        self.winning_idx = random.randint(0, 2)
        for index in range(3):
            button = discord.ui.Button(emoji="<:lootbox:1485614292664320070>", style=discord.ButtonStyle.secondary)
            button.callback = self._make_callback(index)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            for item_index, child in enumerate(self.children):
                if item_index == self.winning_idx:
                    child.emoji = "💎"
                    child.style = discord.ButtonStyle.success
                else:
                    child.emoji = "<:close:1485598320935174317>"
                    child.style = discord.ButtonStyle.danger

            if index == self.winning_idx:
                embed = _result_embed("<:check:1485597845883981905> Відгадав!", "success", "Ти знайшов приз.")
                await self.finish(interaction, "win", embed)
            else:
                embed = _result_embed("<:close:1485598320935174317> Пусто!", "error", "Ти не вгадав коробочку.")
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
            embed = _result_embed("<:check:1485597845883981905> Перемога!", "success", f"Твій кидок: **{user_roll}**\nКидок суперника: **{bot_roll}**")
            await self.finish(interaction, "win", embed)
        elif user_roll < bot_roll:
            embed = _result_embed("<:close:1485598320935174317> Поразка!", "error", f"Твій кидок: **{user_roll}**\nКидок суперника: **{bot_roll}**")
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
                await self.finish(interaction, "win", _result_embed("<:check:1485597845883981905> Знайшов зайве!", "success"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:close:1485598320935174317> Промах!", "error"))

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
                await self.finish(interaction, "win", _result_embed("<:check:1485597845883981905> Правильно!", "success", f"Слово було: **{self.word}**"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:close:1485598320935174317> Помилка!", "error", f"Слово було: **{self.word}**"))

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
                await self.finish(interaction, "win", _result_embed("<:check:1485597845883981905> Вірно!", "success", f"Відповідь: **{answer}**"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:close:1485598320935174317> Невірно!", "error", f"Правильна: **{answer}**"))

        return callback


class TypingModal(discord.ui.Modal, title="Швидкий друк"):
    word_input = discord.ui.TextInput(label="Введіть слово", placeholder="...", required=True)

    def __init__(self, expected_word: str, finish_callback):
        super().__init__()
        self.expected_word = expected_word
        self.finish_callback = finish_callback

    async def on_submit(self, interaction: discord.Interaction):
        if self.word_input.value.strip().lower() == self.expected_word.lower():
            await self.finish_callback(interaction, "win", _result_embed("<:check:1485597845883981905> Вірно надруковано!", "success"))
        else:
            await self.finish_callback(
                interaction,
                "lose",
                _result_embed("<:close:1485598320935174317> Помилка в слові!", "error", f"Очікувалось: **{self.expected_word}**"),
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
                await self.finish(interaction, "win", _result_embed("<:check:1485597845883981905> Вгадав число!", "success"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:close:1485598320935174317> Не вгадав!", "error", f"Було число **{self.winner}**"))

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
                await self.finish(interaction, "win", _result_embed("<:check:1485597845883981905> Швидка реакція!", "success"))
            else:
                await self.finish(interaction, "lose", _result_embed("<:close:1485598320935174317> Натиснув не туди!", "error"))

        return callback


def get_random_minigame(owner_id: int, stake: int, eco: dict, on_complete) -> tuple[discord.Embed, discord.ui.View]:
    enabled_keys = eco.get(
        "enabled_minigames",
        ["math", "higher_lower", "shell", "dice", "odd_emoji", "unscramble", "trivia", "typing", "guess", "reaction"],
    )

    all_games = [
        {"id": "math", "class": MathQuizView, "title": "🧮 Математика", "desc": "Розв'яжи приклад за 15 секунд."},
        {"id": "higher_lower", "class": HigherLowerView, "title": "📈 Більше чи менше", "desc": "Наступне число буде вище чи нижче."},
        {"id": "shell", "class": ShellGameView, "title": "<:lootbox:1485614292664320070> Наперстки", "desc": "Вгадай, де захований діамант."},
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
    if selected["id"] == "math":
        view = selected["class"](owner_id, stake, on_complete, profile="default")
    else:
        view = selected["class"](owner_id, stake, on_complete)

    embed = surface_embed("gameplay", selected["title"], selected["desc"], tone="warning")
    if isinstance(view, HigherLowerView):
        embed.description += f"\n\nПоточне число: **{view.base_num}**"
    elif isinstance(view, MathQuizView):
        embed.description = f"{view.desc}\n\n**{view.question}**"
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
