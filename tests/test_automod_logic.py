import sys
import unittest


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from services.automod import (  # noqa: E402
    find_matching_rule,
    match_custom_rule,
    normalize_string,
    rule_matcher,
    rule_scope_allows,
    rule_targets,
)


class NormalizeStringTests(unittest.TestCase):
    def test_normalize_string_strips_symbols_and_uppercases(self) -> None:
        self.assertEqual(normalize_string("Scam!!! 123"), "SCAM123")

    def test_normalize_string_handles_empty_input(self) -> None:
        self.assertEqual(normalize_string(""), "")


class RuleHelpersTests(unittest.TestCase):
    def test_rule_targets_falls_back_to_both_for_unknown_value(self) -> None:
        self.assertEqual(rule_targets({"target": "weird"}), "both")

    def test_rule_matcher_falls_back_to_contains_for_unknown_value(self) -> None:
        self.assertEqual(rule_matcher({"match": "weird"}), "contains")

    def test_rule_scope_allows_when_scope_matches(self) -> None:
        allowed = rule_scope_allows(
            {
                "only_channels": [100],
                "ignore_channels": [200],
                "only_roles": [10],
                "ignore_roles": [20],
            },
            channel_id=100,
            role_ids={10, 30},
        )
        self.assertTrue(allowed)

    def test_rule_scope_blocks_channel_outside_only_channels(self) -> None:
        allowed = rule_scope_allows({"only_channels": [100]}, channel_id=999, role_ids=set())
        self.assertFalse(allowed)

    def test_rule_scope_blocks_when_ignored_role_present(self) -> None:
        allowed = rule_scope_allows({"ignore_roles": [20]}, channel_id=100, role_ids={20, 30})
        self.assertFalse(allowed)


class CustomRuleMatchingTests(unittest.TestCase):
    def test_contains_match_normalizes_text_before_comparing(self) -> None:
        matched = match_custom_rule({"trigger": "scam", "match": "contains"}, "s.c.a.m!!!")
        self.assertTrue(matched)

    def test_exact_match_requires_full_normalized_match(self) -> None:
        self.assertTrue(match_custom_rule({"trigger": "jackpot", "match": "exact"}, "Jackpot!!!"))
        self.assertFalse(
            match_custom_rule({"trigger": "jackpot", "match": "exact"}, "Huge jackpot!!!")
        )

    def test_match_custom_rule_rejects_blank_trigger(self) -> None:
        self.assertFalse(match_custom_rule({"trigger": "   "}, "anything"))

    def test_find_matching_rule_respects_target_and_scope(self) -> None:
        rules = [
            {
                "trigger": "scam",
                "target": "profile",
            },
            {
                "trigger": "scam",
                "target": "message",
                "only_channels": [555],
                "only_roles": [7],
            },
        ]

        matched = find_matching_rule(
            rules,
            "This looks like a scam",
            target="message",
            channel_id=555,
            role_ids={7},
        )

        self.assertEqual(matched, rules[1])

    def test_find_matching_rule_returns_none_when_no_rule_matches(self) -> None:
        matched = find_matching_rule(
            [{"trigger": "scam", "target": "message", "ignore_channels": [100]}],
            "This is scam",
            target="message",
            channel_id=100,
            role_ids=set(),
        )
        self.assertIsNone(matched)


if __name__ == "__main__":
    unittest.main()
