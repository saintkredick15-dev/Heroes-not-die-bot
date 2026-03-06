import random

# ── Daily templates ────────────────────────────────────────────────────────────
DAILY_TEMPLATES = [
    ("work", 4, 15, [
        "Відпрацюй {target} змін на легкій роботі.",
        "Проведи {target} годин на робочому місці (команда work).",
        "Стань працівником дня: виконай {target} робочих завдань.",
        "Трудоголік: відпрацюй {target} разів без скарг.",
        "Зароби копійчину: {target} успішних виходів на роботу."
    ]),
    ("gambling", 5, 20, [
        "Зіграй у будь-яку азартну гру {target} разів.",
        "Спробуй свою удачу в казино {target} разів.",
        "Крути слоти або кидай кості {target} разів.",
        "Ні дня без ризику: зроби {target} ставок.",
        "Перевір прихильність фортуни: {target} азартних ігор."
    ]),
    ("crime", 2, 6, [
        "Переступи межу закону {target} рази.",
        "Здійсни {target} успішних кримінальних справ.",
        "Стань загрозою міста: {target} краймів за день.",
        "Швидкі гроші: {target} вуличних злочинів."
    ]),
    ("duel", 2, 6, [
        "Виклич або прийми виклик на {target} дуелі.",
        "Проведи {target} дуелей з іншими гравцями.",
        "Гладіатор: {target} дуелей за день.",
        "Докажи свою силу: бийся {target} разів."
    ]),
    ("economy.deposit", 2, 8, [
        "Зроби {target} депозитів до банку.",
        "Поклади гроші на банківський рахунок {target} разів.",
        "Потурбуйся про майбутнє: {target} переводів у банк."
    ]),
    ("economy.rob", 1, 4, [
        "Спробуй вкрасти гроші у сусідів {target} разів.",
        "Здійсни {target} замахів на чужі гаманці.",
        "Стань кишенькарем: {target} спроб пограбування."
    ]),
    ("economy.daily", 1, 1, [
        "Не забудь забрати свій щоденний бонус.",
        "Відміться в банку і отримай щоденну нагороду.",
        "Забери безкоштовні гроші з команди daily."
    ])
]

WEEKLY_TEMPLATES = [
    ("work", 40, 100, [
        "Стань працівником тижня: {target} робочих змін.",
        "Перевиконай план: {target} робочих завдань.",
        "Справжній ветеран праці: {target} змін за тиждень!",
        "Стабільна робота: {target} успішних виходів на зміну."
    ]),
    ("gambling", 50, 200, [
        "Хайролер: зроби {target} ставок у казино!",
        "Залежність чи талант? {target} ігор у казино.",
        "Довга гра: {target} ставок за сім днів.",
        "Король азарту: відіграй {target} партій!"
    ]),
    ("crime", 10, 40, [
        "Гроза району: {target} кримінальних справ.",
        "Мафіозі тижня: {target} успішних краймів.",
        "Хрещений батько: підтверди статус {target} краймами!"
    ]),
    ("duel", 15, 60, [
        "Чемпіон арени: проведи {target} дуелей.",
        "Легенда боїв: {target} дуелей без відпочинку!"
    ]),
    ("economy.rob", 8, 25, [
        "Майстерний крадій: {target} спроб пограбування гравців.",
        "Бандит: спустошуй кишені {target} разів."
    ]),
    ("economy.deposit", 15, 50, [
        "Фінансовий магнат: {target} депозитів у банк.",
        "Банкір: зроби {target} вкладів на депозитний рахунок."
    ])
]

def _max_feasible(action: str, eco: dict) -> int | None:
    """
    Розраховує максимальну кількість разів, що можна виконати дію за 1 добу.
    Повертає None якщо дія взагалі недоступна на цьому сервері.
    """
    match action:
        case "crime":
            if not eco.get("crime_enabled", True):
                return None
            cd = eco.get("crime_cooldown", 28800)
            return max(1, int(86400 / cd)) if cd > 0 else 99
        case "work":
            cd = eco.get("work_cooldown", 14400)
            return max(1, int(86400 / cd)) if cd > 0 else 99
        case "economy.daily":
            return 1
        case "economy.rob":
            if not eco.get("rob_enabled", True):
                return None
            cd = eco.get("rob_cooldown", 3600)
            return max(1, int(86400 / cd)) if cd > 0 else 99
        case "duel":
            if not eco.get("duel_enabled", True):
                return None
            return 99
        case _:
            return 99  

def _max_feasible_weekly(action: str, eco: dict) -> int | None:
    """
    Максимальна кількість виконань дії за 7 днів (для weekly квестів).
    """
    daily = _max_feasible(action, eco)
    if daily is None:
        return None
    return daily * 7

def generate_dynamic_pool(q_type: str, count: int, eco: dict) -> list[dict]:
    """Генерує count унікальних квестів, враховуючи eco налаштування."""
    import time as _t
    templates = DAILY_TEMPLATES if q_type == "daily" else WEEKLY_TEMPLATES
    random.shuffle(templates)
    is_weekly = (q_type == "weekly")

    feasible = []
    for tpl in templates:
        action = tpl[0]
        max_f  = _max_feasible_weekly(action, eco) if is_weekly else _max_feasible(action, eco)
        if max_f is not None:
            feasible.append((tpl, max_f))

    if not feasible:
        feasible = [(t, 99) for t in templates if t[0] == "gambling"] or [(templates[0], 99)]

    pool = []
    prefixes = ["", "", "🎯 Завдання: ", "🔥 Виклик: ", "⚡ Місія: "]

    for i in range(count):
        tpl, max_f = feasible[i % len(feasible)]
        action = tpl[0]
        raw_max = tpl[2]
        capped_max = min(raw_max, max_f)
        capped_min = min(tpl[1], capped_max)
        target = random.randint(capped_min, capped_max)

        desc_template = random.choice(tpl[3])
        desc = random.choice(prefixes) + desc_template.format(target=target)
        q_id = f"{q_type[0]}q_{int(_t.time()*1000)}_{i}"

        pool.append({
            "id": q_id,
            "type": q_type,
            "action": action,
            "target": target,
            "desc": desc
        })

    return pool

def get_random_quests(q_type: str, count: int, eco: dict = None, exclude_ids: list[str] = None):
    if eco is None:
        eco = {}
    if exclude_ids is None:
        exclude_ids = []
    return generate_dynamic_pool(q_type, count, eco)

async def setup(bot):
    pass
