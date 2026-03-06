"""
utils/eco_helpers.py
Спільні утиліти для економічних команд (DRY).
"""
import time as _time


def make_log(amount: int, desc: str) -> dict:
    """
    Створює запис для eco_history.
    🟢 для доходу, 🔴 для витрат.
    """
    now   = int(_time.time())
    color = "🟢" if amount >= 0 else "🔴"
    return {"log": f"{color} **{abs(amount)}** | {desc} | <t:{now}:t>"}
