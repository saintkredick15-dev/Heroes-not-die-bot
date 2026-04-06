import sys
import unittest
from types import SimpleNamespace


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from commands.activity.leaderboard import build_eco_embed, build_xp_embed  # noqa: E402


class LeaderboardPeriodTests(unittest.TestCase):
    def test_week_mode_uses_period_counters_in_description(self) -> None:
        member = SimpleNamespace(display_name="Kredick")
        entries = [
            (
                1,
                {
                    "level": 7,
                    "xp": 42,
                    "xp_week": 120,
                    "messages": 999,
                    "messages_week": 12,
                    "voice_minutes": 600,
                    "voice_minutes_week": 30,
                    "reactions": 444,
                    "reactions_week": 5,
                },
                member,
            )
        ]

        embed = build_xp_embed(entries, 0, 1, None, 1, entries[0][1], mode="week")

        self.assertIn("+120 XP за 7 днів", embed.description)
        self.assertIn("12", embed.description)
        self.assertIn("0.5h", embed.description)
        self.assertIn("5", embed.description)
        self.assertNotIn("999", embed.description)
        self.assertNotIn("10.0h", embed.description)
        self.assertNotIn("444", embed.description)

    def test_month_mode_uses_period_counters_in_footer(self) -> None:
        member = SimpleNamespace(display_name="Kredick")
        doc = {
            "level": 9,
            "xp": 99,
            "xp_month": 345,
            "messages_month": 21,
            "voice_minutes_month": 120,
            "reactions_month": 8,
        }
        entries = [(3, doc, member)]

        embed = build_xp_embed(entries, 0, 1, None, 3, doc, mode="month")

        self.assertEqual(embed.footer.text, "Ти #3 — рівень 9 — +345 XP за 30 днів")

    def test_eco_week_mode_uses_rolling_period_value(self) -> None:
        member = SimpleNamespace(display_name="Kredick")
        doc = {
            "_eco_week_earned": 321,
            "wallet": 100,
            "bank": 50,
        }
        entries = [(1, doc, member)]

        embed = build_eco_embed(
            entries,
            0,
            1,
            None,
            1,
            doc,
            {"currency_emoji": "$", "currency_name": "Coin"},
            mode="week",
        )

        self.assertIn("321", embed.description)
        self.assertIn("за 7 днів", embed.description)
        self.assertNotIn("in 7d", embed.description)
        self.assertEqual(embed.footer.text, "Ти #1 — 321 Coin за 7 днів")

    def test_eco_month_mode_uses_rolling_period_value(self) -> None:
        member = SimpleNamespace(display_name="Kredick")
        doc = {
            "_eco_month_earned": 987,
            "wallet": 200,
            "bank": 300,
        }
        entries = [(2, doc, member)]

        embed = build_eco_embed(
            entries,
            0,
            1,
            None,
            2,
            doc,
            {"currency_emoji": "$", "currency_name": "Coin"},
            mode="month",
        )

        self.assertIn("987", embed.description)
        self.assertIn("за 30 днів", embed.description)
        self.assertEqual(embed.footer.text, "Ти #2 — 987 Coin за 30 днів")


if __name__ == "__main__":
    unittest.main()
