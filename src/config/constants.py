from enum import Enum
from typing import List

OWNER_IDS: List[int] = [961262391314755665] 

class Colors(Enum):
    
    DEFAULT = 0x2b2d31    
    SUCCESS = 0x57F287    
    ERROR = 0xED4245      
    WARNING = 0xFEE75C    
    INFO = 0x5865F2       
    PREMIUM = 0xFFD700    
    DARK = 0x1A1A2E       

class EcoOptions(Enum):
    
    CRIME_WIN_CHANCE = 0.40
    CRIME_FAIL_CHANCE = 0.40
    CRIME_CRIT_FAIL_CHANCE = 0.15
    CRIME_SPECIAL_CHANCE = 0.05
    
    WORK_EVENT_CHANCE = 0.40
    
    TAX_BRACKET_0 = (0, 0.0)             
    TAX_BRACKET_1 = (100_000, 0.10)      
    TAX_BRACKET_2 = (500_000, 0.25)      
    TAX_BRACKET_3 = (1_000_000, 0.50)    
    TAX_BRACKET_4 = (5_000_000, 0.75)    

    ACCOUNT_AGE_MIN_DAYS = 14  

    DEFAULT_INFLATION_LIMIT = 3.0

class Emojis(Enum):

    # ── Статуси ──────────────────────────────────────────────────────────────
    CHECK       = "<:cutiecheckmark:1479120440734650389>"
    CROSS       = "<:cutiex:1480246146076119132>"
    WARN        = "<:warn:1477376152191373504>"
    HOURGLASS   = "<:Hourglass:1479950504321745026>"
    TRASH       = "<:trash:1477722148071145634>"
    INBOX       = "<:inbox:1479128004847341620>"

    # ── Нагороди / Рейтинг ───────────────────────────────────────────────────
    TROPHY      = "<:trophy:1475953207782932602>"
    MEDAL       = "<:medal:1475953523039408360>"
    FIRECRACKER = "<:firecracker:1479953348185555077>"

    # ── Економіка ────────────────────────────────────────────────────────────
    COIN      = "<:coin:1478487028105482485>"
    COINS     = "<:Coins:1478486725113286899>"
    BANK      = "<:bank:1478483868867891261>"
    LOOTBOX   = "<:openlootbox:1479952212980535498>"
    GIFT      = "<:gifttop:1479952511635820586>"
    SHIELD    = "<:shield:1478800925664612372>"
    STAR      = "<:reactionstar:1475954213455532067>"
    CRIMEPASS = "<:crimepass:1479951455543889970>"

    # ── Робота / Злочин ──────────────────────────────────────────────────────
    CLOCK   = "<:clock:1476209087804084328>"
    FLAME   = "<:flame:1478490474145906800>"
    WORK    = "<:work:1478489752020975626>"
    WORKS   = "<:works:1478510456971857992>"
    ROBBERY = "<:robbery:1478496325887725814>"

    # ── Навігація ────────────────────────────────────────────────────────────
    LEFT    = "<:totheleft:1478825190749110323>"
    HISTORY = "<:historylist:1478824658332684510>"
    SLOTS   = "<:slot_machine:1479149411832565841>"
    HELP    = "<:reasonqiestion:1476209697919860777>"

    # ── Адмін / Дев ──────────────────────────────────────────────────────────
    DEV_STATS = "<:statistics:1477721796857041067>"
    GLOBE     = "<:planet:1479905429055340564>"
    LOCK      = "<:lockopen:1479905741874921672>"
    UNLOCK    = "<:lock:1479905802318774505>"
