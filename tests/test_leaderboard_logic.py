import sys
import unittest
from types import SimpleNamespace


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from commands.activity.leaderboard import build_xp_embed  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
