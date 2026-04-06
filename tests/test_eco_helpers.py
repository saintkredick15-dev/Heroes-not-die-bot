import sys
import unittest
from datetime import datetime, timedelta, timezone


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from utils.eco_helpers import add_daily_earnings_inc, sum_recent_daily_earnings  # noqa: E402


class EconomyDailyEarningsTests(unittest.TestCase):
    def test_add_daily_earnings_inc_writes_utc_day_key(self) -> None:
        inc_query = {"wallet": 50}
        timestamp = int(datetime(2026, 4, 6, 14, 30, tzinfo=timezone.utc).timestamp())

        add_daily_earnings_inc(inc_query, 75, timestamp=timestamp)

        self.assertEqual(inc_query["wallet"], 50)
        self.assertEqual(inc_query["economy_daily_earnings.2026-04-06"], 75)

    def test_sum_recent_daily_earnings_uses_rolling_window(self) -> None:
        now = int(datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc).timestamp())
        old_day = (datetime(2026, 4, 6, tzinfo=timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")

        doc = {
            "economy_daily_earnings": {
                "2026-04-06": 100,
                "2026-04-05": 50,
                "2026-04-01": 25,
                old_day: 999,
            }
        }

        self.assertEqual(sum_recent_daily_earnings(doc, 7, timestamp=now), 175)
        self.assertEqual(sum_recent_daily_earnings(doc, 30, timestamp=now), 1174)


if __name__ == "__main__":
    unittest.main()
