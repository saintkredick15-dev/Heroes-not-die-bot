import sys
import unittest


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from services.moderation import (  # noqa: E402
    _format_duration,
    _log_key_for_source,
    _parse_duration_to_seconds,
    _source_label,
)


class ParseDurationTests(unittest.TestCase):
    def test_parse_duration_supports_minutes_hours_days(self) -> None:
        self.assertEqual(_parse_duration_to_seconds("30m"), 1800)
        self.assertEqual(_parse_duration_to_seconds("2h"), 7200)
        self.assertEqual(_parse_duration_to_seconds("1d"), 86400)

    def test_parse_duration_treats_plain_number_as_hours(self) -> None:
        self.assertEqual(_parse_duration_to_seconds("12"), 43200)

    def test_parse_duration_rejects_invalid_input(self) -> None:
        self.assertIsNone(_parse_duration_to_seconds("bad"))
        self.assertIsNone(_parse_duration_to_seconds("15w"))


class FormatDurationTests(unittest.TestCase):
    def test_format_duration_prefers_days_hours_minutes(self) -> None:
        self.assertEqual(_format_duration(86400), "1 дн.")
        self.assertEqual(_format_duration(7200), "2 год.")
        self.assertEqual(_format_duration(1800), "30 хв.")

    def test_format_duration_falls_back_to_seconds(self) -> None:
        self.assertEqual(_format_duration(45), "45 с.")


class SourceMappingTests(unittest.TestCase):
    def test_source_label_returns_expected_human_labels(self) -> None:
        self.assertEqual(_source_label("manual"), "Модераторська команда")
        self.assertEqual(_source_label("auto"), "Автомод")
        self.assertEqual(_source_label("escalation"), "Авто-ескалація")
        self.assertEqual(_source_label("other"), "Система")

    def test_log_key_mapping_uses_auto_channel_for_auto_and_escalation(self) -> None:
        self.assertEqual(_log_key_for_source("manual"), "log_mod_action")
        self.assertEqual(_log_key_for_source("auto"), "log_mod_auto")
        self.assertEqual(_log_key_for_source("escalation"), "log_mod_auto")


if __name__ == "__main__":
    unittest.main()
