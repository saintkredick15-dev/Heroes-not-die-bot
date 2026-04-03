import sys
import unittest


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from commands.moderation.mod import _extract_user_id  # noqa: E402


class ExtractUserIdTests(unittest.TestCase):
    def test_extract_user_id_accepts_raw_numeric_id(self) -> None:
        self.assertEqual(_extract_user_id("1234567890"), 1234567890)

    def test_extract_user_id_accepts_mentions(self) -> None:
        self.assertEqual(_extract_user_id("<@1234567890>"), 1234567890)
        self.assertEqual(_extract_user_id("<@!1234567890>"), 1234567890)

    def test_extract_user_id_rejects_invalid_values(self) -> None:
        self.assertIsNone(_extract_user_id("abc"))
        self.assertIsNone(_extract_user_id("<@!abc>"))


if __name__ == "__main__":
    unittest.main()
