import sys
import unittest
from datetime import datetime, timedelta, timezone


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from commands.administration.logs_setup import _stats_publication_state  # noqa: E402


class LogsSetupPublicationStateTests(unittest.TestCase):
    def test_stats_publication_state_handles_missing_last_post(self) -> None:
        last_post, next_post = _stats_publication_state({"stats_interval_days": 7})

        self.assertEqual(last_post, "Ще не публікувався")
        self.assertIn("7 дн.", next_post)

    def test_stats_publication_state_builds_last_and_next_timestamps(self) -> None:
        now = datetime(2026, 4, 7, 15, 0, tzinfo=timezone.utc)
        settings = {
            "stats_interval_days": 5,
            "stats_last_post": now.timestamp(),
        }

        last_post, next_post = _stats_publication_state(settings)
        expected_next = now + timedelta(days=5)

        self.assertEqual(last_post, f"<t:{int(now.timestamp())}:f> • <t:{int(now.timestamp())}:R>")
        self.assertEqual(next_post, f"<t:{int(expected_next.timestamp())}:f> • <t:{int(expected_next.timestamp())}:R>")


if __name__ == "__main__":
    unittest.main()
