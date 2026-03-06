import discord
import random
import asyncio

class BaseMinigame(discord.ui.View):
    def __init__(self, owner_id: int, stake: int, on_complete, timeout=15):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.stake = stake
        self.on_complete = on_complete
        self.finished = False

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.owner_id:
            await i.response.send_message("❌ Це не твоя гра!", ephemeral=True)
            return False
        return True

    async def finish(self, i: discord.Interaction, outcome: str, embed: discord.Embed):
        if self.finished: return
        self.finished = True
        for c in self.children: 
            if hasattr(c, "disabled"):
                c.disabled = True
        try:
            await self.on_complete(i, outcome, embed, self)
        except Exception:
            pass
            
    async def on_timeout(self):
        if not self.finished:
            self.finished = True
            for c in self.children: 
                if hasattr(c, "disabled"):
                    c.disabled = True
            try:
                
                await self.on_complete(None, "lose", discord.Embed(title="⏰ Час вийшов!", description="Ви нічого не обрали.", color=0xed4245), self)
            except:
                pass

class MathQuizView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        a = random.randint(10, 50)
        b = random.randint(10, 50)
        op = random.choice(["+", "-"])
        self.answer = a + b if op == "+" else a - b
        
        self.question = f"{a} {op} {b} = ?"
        
        choices = [self.answer, self.answer + random.randint(1, 10), self.answer - random.randint(1, 10), self.answer + random.randint(-5, 5)]
        choices = list(set(choices))
        while len(choices) < 3:
            choices.append(self.answer + random.randint(10, 20))
            choices = list(set(choices))
        random.shuffle(choices)
        
        for c in choices[:3]:
            btn = discord.ui.Button(label=str(c), style=discord.ButtonStyle.primary)
            btn.callback = self._make_callback(c)
            self.add_item(btn)

    def _make_callback(self, val: int):
        async def cb(i: discord.Interaction):
            if val == self.answer:
                embed = discord.Embed(title="✅ Вірно!", description=f"{self.question} {self.answer}", color=0x57f287)
                await self.finish(i, "win", embed)
            else:
                embed = discord.Embed(title="❌ Помилка!", description=f"Правильна відповідь: {self.answer}", color=0xed4245)
                await self.finish(i, "lose", embed)
        return cb

class HigherLowerView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        self.base_num = random.randint(20, 80)
        self.secret = random.randint(1, 100)
        
        while self.secret == self.base_num:
            self.secret = random.randint(1, 100)

    @discord.ui.button(label="Більше ⬆️", style=discord.ButtonStyle.success)
    async def btn_high(self, i: discord.Interaction, b: discord.ui.Button):
        await self._check(i, self.secret > self.base_num)

    @discord.ui.button(label="Менше ⬇️", style=discord.ButtonStyle.danger)
    async def btn_low(self, i: discord.Interaction, b: discord.ui.Button):
        await self._check(i, self.secret < self.base_num)

    async def _check(self, i: discord.Interaction, is_correct: bool):
        if is_correct:
            embed = discord.Embed(title="✅ Вгадав!", description=f"Наступне число було **{self.secret}**", color=0x57f287)
            await self.finish(i, "win", embed)
        else:
            embed = discord.Embed(title="❌ Не вгадав!", description=f"Наступне число було **{self.secret}**", color=0xed4245)
            await self.finish(i, "lose", embed)

class ShellGameView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        self.winning_idx = random.randint(0, 2)
        
        for idx in range(3):
            btn = discord.ui.Button(emoji="📦", style=discord.ButtonStyle.secondary)
            btn.callback = self._make_callback(idx)
            self.add_item(btn)

    def _make_callback(self, idx: int):
        async def cb(i: discord.Interaction):
            for j, c in enumerate(self.children):
                if j == self.winning_idx:
                    c.emoji = "💎"
                    c.style = discord.ButtonStyle.success
                else:
                    c.emoji = "❌"
                    c.style = discord.ButtonStyle.danger
            
            if idx == self.winning_idx:
                embed = discord.Embed(title="✅ Відгадав!", description="Ти знайшов приз!", color=0x57f287)
                await self.finish(i, "win", embed)
            else:
                embed = discord.Embed(title="❌ Пусто!", description="Ти не вгадав коробочку.", color=0xed4245)
                await self.finish(i, "lose", embed)
        return cb

class DiceDuelView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)

    @discord.ui.button(label="Кинути кубики 🎲", style=discord.ButtonStyle.primary)
    async def roll(self, i: discord.Interaction, b: discord.ui.Button):
        user_roll = random.randint(2, 12)
        bot_roll = random.randint(2, 12)
        
        if user_roll > bot_roll:
            embed = discord.Embed(title="✅ Перемога!", description=f"Твій кидок: **{user_roll}**\nКидок суперника: **{bot_roll}**", color=0x57f287)
            await self.finish(i, "win", embed)
        elif user_roll < bot_roll:
            embed = discord.Embed(title="❌ Поразка!", description=f"Твій кидок: **{user_roll}**\nКидок суперника: **{bot_roll}**", color=0xed4245)
            await self.finish(i, "lose", embed)
        else:
            embed = discord.Embed(title="🤝 Нічия!", description=f"Обидва кинули **{user_roll}**", color=0xffff00)
            await self.finish(i, "draw", embed)

class OddEmojiView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=12)
        pairs = [("🍎", "🍅"), ("😀", "😃"), ("🦊", "🐺"), ("⚽", "🏀"), ("🚗", "🚜")]
        base_em, odd_em = random.choice(pairs)
        self.odd_idx = random.randint(0, 4)
        
        for idx in range(5):
            em = odd_em if idx == self.odd_idx else base_em
            btn = discord.ui.Button(emoji=em, style=discord.ButtonStyle.secondary)
            btn.callback = self._make_callback(idx)
            self.add_item(btn)

    def _make_callback(self, idx: int):
        async def cb(i: discord.Interaction):
            if idx == self.odd_idx:
                embed = discord.Embed(title="✅ Знайшов зайве!", color=0x57f287)
                await self.finish(i, "win", embed)
            else:
                embed = discord.Embed(title="❌ Промах!", color=0xed4245)
                await self.finish(i, "lose", embed)
        return cb

class UnscrambleView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        words = ["економіка", "циган", "монета", "капітал", "робота", "банк", "сейф", "податок"]
        self.word = random.choice(words)
        
        l = list(self.word)
        random.shuffle(l)
        while "".join(l) == self.word:
            random.shuffle(l)
        self.scrambled = "".join(l).upper()
        
        choices = [self.word]
        while len(choices) < 4:
            c = random.choice(words)
            if c not in choices:
                choices.append(c)
        random.shuffle(choices)
        
        for c in choices:
            btn = discord.ui.Button(label=c.capitalize(), style=discord.ButtonStyle.primary)
            btn.callback = self._make_callback(c)
            self.add_item(btn)

    def _make_callback(self, c: str):
        async def cb(i: discord.Interaction):
            if c == self.word:
                embed = discord.Embed(title="✅ Правильно!", description=f"Слово було: **{self.word}**", color=0x57f287)
                await self.finish(i, "win", embed)
            else:
                embed = discord.Embed(title="❌ Помилка!", description=f"Слово було: **{self.word}**", color=0xed4245)
                await self.finish(i, "lose", embed)
        return cb

class TriviaView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        qs = [
            ("Скільки днів у високосному році?", "366", ["365", "364", "367"]),
            ("Хто намалював Мону Лізу?", "Да Вінчі", ["Пікассо", "Ван Гог", "Далі"]),
            ("Скільки континентів на Землі?", "7", ["5", "6", "8"]),
            ("Як називається найдовша річка?", "Ніл", ["Амазонка", "Дніпро", "Міссісіпі"]),
            ("Що більше важить: кілограм вати чи цвяхів?", "Однаково", ["Цвяхи", "Вата", "Невідомо"])
        ]
        q, a, wrong = random.choice(qs)
        self.question = q
        
        choices = wrong + [a]
        random.shuffle(choices)
        
        for c in choices:
            btn = discord.ui.Button(label=c, style=discord.ButtonStyle.primary)
            btn.callback = self._make_callback(c == a, a)
            self.add_item(btn)

    def _make_callback(self, correct: bool, ans: str):
        async def cb(i: discord.Interaction):
            if correct:
                embed = discord.Embed(title="✅ Вірно!", description=f"Відповідь: **{ans}**", color=0x57f287)
                await self.finish(i, "win", embed)
            else:
                embed = discord.Embed(title="❌ Невірно!", description=f"Правильна: **{ans}**", color=0xed4245)
                await self.finish(i, "lose", embed)
        return cb

class TypingModal(discord.ui.Modal, title="Швидкий друк"):
    word_input = discord.ui.TextInput(label="Введіть слово", placeholder="...", required=True)

    def __init__(self, expected_word: str, finish_callback):
        super().__init__()
        self.expected_word = expected_word
        self.finish_callback = finish_callback

    async def on_submit(self, interaction: discord.Interaction):
        if self.word_input.value.strip().lower() == self.expected_word.lower():
            embed = discord.Embed(title="✅ Вірно надруковано!", color=0x57f287)
            await self.finish_callback(interaction, "win", embed)
        else:
            embed = discord.Embed(title="❌ Помилка в слові!", description=f"Очікувалось: **{self.expected_word}**", color=0xed4245)
            await self.finish_callback(interaction, "lose", embed)

class TypingTestView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=15)
        self.word = random.choice(["інвестор", "криптовалюта", "дивіденди", "активи", "блокчейн"])
        self.desc = f"Надрукуй слово без помилок:\n\n# {self.word}"

    @discord.ui.button(label="Надрукувати ⌨️", style=discord.ButtonStyle.primary)
    async def btn_type(self, i: discord.Interaction, b: discord.ui.Button):
        modal = TypingModal(self.word, self.finish)
        await i.response.send_modal(modal)

class GuessNumberView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=12)
        self.winner = random.randint(1, 5)
        for num in range(1, 6):
            btn = discord.ui.Button(label=str(num), style=discord.ButtonStyle.secondary)
            btn.callback = self._make_callback(num)
            self.add_item(btn)

    def _make_callback(self, num: int):
        async def cb(i: discord.Interaction):
            for c in self.children:
                if int(c.label) == self.winner: c.style = discord.ButtonStyle.success
                else: c.style = discord.ButtonStyle.danger
            if num == self.winner:
                embed = discord.Embed(title="✅ Вгадав число!", color=0x57f287)
                await self.finish(i, "win", embed)
            else:
                embed = discord.Embed(title="❌ Не вгадав!", description=f"Було число **{self.winner}**", color=0xed4245)
                await self.finish(i, "lose", embed)
        return cb

class ReactionTestView(BaseMinigame):
    def __init__(self, owner_id: int, stake: int, on_complete):
        super().__init__(owner_id, stake, on_complete, timeout=10)
        self.green_idx = random.randint(0, 3)
        for idx in range(4):
            style = discord.ButtonStyle.success if idx == self.green_idx else discord.ButtonStyle.secondary
            btn = discord.ui.Button(label="ТИСНИ" if idx == self.green_idx else "Ні", style=style)
            btn.callback = self._make_callback(idx)
            self.add_item(btn)

    def _make_callback(self, idx: int):
        async def cb(i: discord.Interaction):
            if idx == self.green_idx:
                embed = discord.Embed(title="✅ Швидка реакція!", color=0x57f287)
                await self.finish(i, "win", embed)
            else:
                embed = discord.Embed(title="❌ Натиснув не туди!", color=0xed4245)
                await self.finish(i, "lose", embed)
        return cb

def get_random_minigame(owner_id: int, stake: int, eco: dict, on_complete) -> tuple[discord.Embed, discord.ui.View]:
    enabled_keys = eco.get("enabled_minigames", ["math", "higher_lower", "shell", "dice", "odd_emoji", "unscramble", "trivia", "typing", "guess", "reaction"])
    
    all_games = [
        {"id": "math", "class": MathQuizView, "title": "🧮 Математика", "desc": "Розв'яжи приклад за 15 секунд!"},
        {"id": "higher_lower", "class": HigherLowerView, "title": "📈 Більше Менше", "desc": "Наступне число буде Більше чи Менше ❓"},
        {"id": "shell", "class": ShellGameView, "title": "📦 Наперстки", "desc": "Вгадай, де захований діамант!"},
        {"id": "dice", "class": DiceDuelView, "title": "🎲 Кості", "desc": "Кинь кості! Потрібно викинути більше за суперника."},
        {"id": "odd_emoji", "class": OddEmojiView, "title": "🔍 Зайвий Емодзі", "desc": "Знайди зайвий емодзі серед усіх за 12 секунд!"},
        {"id": "unscramble", "class": UnscrambleView, "title": "🔤 Анаграма", "desc": "Знайди правильне слово серед варіантів."},
        {"id": "trivia", "class": TriviaView, "title": "🧠 Вікторина", "desc": "Обери правильну відповідь на питання."},
        {"id": "typing", "class": TypingTestView, "title": "⌨️ Швидкий друк", "desc": "Надрукуй слово без помилок."},
        {"id": "guess", "class": GuessNumberView, "title": "🔢 Відгадай число", "desc": "Яке з чисел від 1 до 5 я загадав?"},
        {"id": "reaction", "class": ReactionTestView, "title": "⚡ Реакція", "desc": "Якнайшвидше натисни ЗЕЛЕНУ кнопку!"}
    ]
    
    games = [g for g in all_games if g["id"] in enabled_keys]
    if not games:
        games = all_games 

    g = random.choice(games)
    view = g["class"](owner_id, stake, on_complete)
    
    embed = discord.Embed(title=g["title"], description=g["desc"], color=0xffa500)
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
        
    return embed, view

async def setup(bot):
    pass
