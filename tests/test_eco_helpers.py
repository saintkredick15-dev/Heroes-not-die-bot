import sys
import unittest
from unittest import mock


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from utils.eco_helpers import calculate_tax, fmt_duration, make_log  # noqa: E402


class MakeLogTests(unittest.TestCase):
    @mock.patch("utils.eco_helpers._time.time", return_value=1234567890)
    def test_make_log_uses_plus_marker_for_positive_amount(self, _: mock.Mock) -> None:
        item = make_log(25, "Daily reward")

        self.assertIn("**25**", item["log"])
        self.assertIn("Daily reward", item["log"])
        self.assertIn("<t:1234567890:t>", item["log"])

    @mock.patch("utils.eco_helpers._time.time", return_value=1234567890)
    def test_make_log_uses_minus_marker_for_negative_amount(self, _: mock.Mock) -> None:
        item = make_log(-25, "Transfer")

        self.assertIn("**25**", item["log"])
        self.assertIn("Transfer", item["log"])


class FormatDurationTests(unittest.TestCase):
    def test_fmt_duration_formats_hours_and_minutes(self) -> None:
        self.assertEqual(fmt_duration(5400), "1г 30хв")

    def test_fmt_duration_formats_minutes_only(self) -> None:
        self.assertEqual(fmt_duration(1200), "20хв")


class CalculateTaxTests(unittest.TestCase):
    def test_calculate_tax_uses_first_wealth_bracket(self) -> None:
        net, tax, label = calculate_tax(base_amount=1000, wallet=100_000, bank=0)

        self.assertEqual(net, 900)
        self.assertEqual(tax, 100)
        self.assertEqual(label, "10%")

    def test_calculate_tax_uses_highest_matching_bracket(self) -> None:
        net, tax, label = calculate_tax(base_amount=1000, wallet=5_000_000, bank=0)

        self.assertEqual(net, 250)
        self.assertEqual(tax, 750)
        self.assertEqual(label, "75%")

    def test_calculate_tax_returns_zero_tax_below_threshold(self) -> None:
        net, tax, label = calculate_tax(base_amount=1000, wallet=999, bank=0)

        self.assertEqual(net, 1000)
        self.assertEqual(tax, 0)
        self.assertEqual(label, "0%")


if __name__ == "__main__":
    unittest.main()
