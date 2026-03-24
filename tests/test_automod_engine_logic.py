import sys
import unittest
from unittest import mock


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from events import automod_engine as engine_mod  # noqa: E402
from events.automod_engine import AutomodEngine  # noqa: E402


class AutomodEngineCacheIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        engine_mod._FLOOD_CACHE.clear()
        engine_mod._DUP_CACHE.clear()
        engine_mod._ATTACH_CACHE.clear()
        engine_mod._COOLDOWN.clear()
        self.engine = AutomodEngine(bot=mock.Mock())

    def test_cooldown_is_scoped_per_guild(self) -> None:
        with mock.patch("events.automod_engine.time.time", return_value=100.0):
            self.engine._set_cooldown(1, 50)

        with mock.patch("events.automod_engine.time.time", return_value=105.0):
            self.assertTrue(self.engine._in_cooldown(1, 50))
            self.assertFalse(self.engine._in_cooldown(2, 50))

    def test_duplicate_detection_does_not_mix_guilds(self) -> None:
        timestamps = iter([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

        with mock.patch("events.automod_engine.time.time", side_effect=lambda: next(timestamps)):
            self.assertFalse(self.engine._check_duplicate(1, 99, "spam"))
            self.assertFalse(self.engine._check_duplicate(1, 99, "spam"))
            self.assertFalse(self.engine._check_duplicate(2, 99, "spam"))
            self.assertFalse(self.engine._check_duplicate(2, 99, "spam"))
            self.assertTrue(self.engine._check_duplicate(1, 99, "spam"))
            self.assertTrue(self.engine._check_duplicate(2, 99, "spam"))

    def test_flood_detection_does_not_mix_guilds(self) -> None:
        timestamps = iter([1.0, 2.0, 3.0, 4.0])

        with mock.patch("events.automod_engine.time.time", side_effect=lambda: next(timestamps)):
            self.assertFalse(self.engine._check_flood(1, 77, count=2, interval=5))
            self.assertFalse(self.engine._check_flood(2, 77, count=2, interval=5))
            self.assertTrue(self.engine._check_flood(1, 77, count=2, interval=5))
            self.assertTrue(self.engine._check_flood(2, 77, count=2, interval=5))

    def test_cleanup_state_removes_expired_entries(self) -> None:
        engine_mod._COOLDOWN[(1, 1)] = 10.0
        engine_mod._FLOOD_CACHE[(1, 1)].extend([1.0])
        engine_mod._ATTACH_CACHE[(1, 1)].extend([1.0])
        engine_mod._DUP_CACHE[(1, 1)].extend([("abc", 1.0)])

        self.engine._cleanup_state(now=1_000.0)

        self.assertEqual(dict(engine_mod._COOLDOWN), {})
        self.assertEqual(dict(engine_mod._FLOOD_CACHE), {})
        self.assertEqual(dict(engine_mod._ATTACH_CACHE), {})
        self.assertEqual(dict(engine_mod._DUP_CACHE), {})


if __name__ == "__main__":
    unittest.main()
