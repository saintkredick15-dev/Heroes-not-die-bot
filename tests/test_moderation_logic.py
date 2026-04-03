import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import discord


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from services.moderation import (  # noqa: E402
    _format_duration,
    _log_key_for_source,
    _parse_duration_to_seconds,
    _source_label,
    _warn_case_state,
    build_active_warn_query,
    validate_moderation_target,
)


class FakeRole:
    def __init__(self, position: int):
        self.position = position

    def __ge__(self, other: "FakeRole") -> bool:
        return self.position >= other.position


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


class WarnLifecycleTests(unittest.TestCase):
    def test_warn_case_state_marks_revoked_first(self) -> None:
        case = {"revoked": True, "timestamp": datetime.now(timezone.utc) - timedelta(days=90)}
        self.assertEqual(_warn_case_state(case, 7), "revoked")

    def test_warn_case_state_marks_decayed_after_cutoff(self) -> None:
        case = {"timestamp": datetime.now(timezone.utc) - timedelta(days=10)}
        self.assertEqual(_warn_case_state(case, 7), "decayed")

    def test_warn_case_state_keeps_recent_warn_active(self) -> None:
        case = {"timestamp": datetime.now(timezone.utc) - timedelta(days=1)}
        self.assertEqual(_warn_case_state(case, 7), "active")

    def test_active_warn_query_excludes_revoked_and_applies_decay(self) -> None:
        now = datetime(2026, 4, 1, tzinfo=timezone.utc)
        query = build_active_warn_query(1, 2, 14, now=now)
        self.assertEqual(query["guild_id"], 1)
        self.assertEqual(query["user_id"], 2)
        self.assertEqual(query["action"], "warn")
        self.assertEqual(query["revoked"], {"$ne": True})
        self.assertEqual(query["timestamp"]["$gte"], now - timedelta(days=14))


class ValidationTests(unittest.TestCase):
    def _guild(self):
        bot_member = SimpleNamespace(
            id=999,
            top_role=FakeRole(50),
            guild_permissions=discord.Permissions(moderate_members=True, kick_members=True, ban_members=True),
        )
        return SimpleNamespace(owner_id=1, me=bot_member)

    def _member(self, user_id: int, role_pos: int, *, bot: bool = False):
        return SimpleNamespace(
            id=user_id,
            bot=bot,
            top_role=FakeRole(role_pos),
            guild_permissions=discord.Permissions.none(),
        )

    def test_validate_blocks_self_target(self) -> None:
        guild = self._guild()
        actor = self._member(10, 40)
        target = self._member(10, 10)
        error = validate_moderation_target(guild=guild, actor=actor, target=target, action="warn")
        self.assertIn("до себе", error)

    def test_validate_blocks_owner_target(self) -> None:
        guild = self._guild()
        actor = self._member(10, 40)
        target = self._member(1, 10)
        error = validate_moderation_target(guild=guild, actor=actor, target=target, action="ban")
        self.assertEqual(error, "Не можна карати власника сервера.")

    def test_validate_blocks_equal_or_higher_role_target(self) -> None:
        guild = self._guild()
        actor = self._member(10, 40)
        target = self._member(11, 40)
        error = validate_moderation_target(guild=guild, actor=actor, target=target, action="kick")
        self.assertEqual(error, "Ціль має рівну або вищу роль, ніж у модератора.")

    def test_validate_blocks_bot_target(self) -> None:
        guild = self._guild()
        actor = self._member(10, 40)
        target = self._member(12, 10, bot=True)
        error = validate_moderation_target(guild=guild, actor=actor, target=target, action="warn")
        self.assertEqual(error, "Бота не можна модерувати цією командою.")


if __name__ == "__main__":
    unittest.main()
