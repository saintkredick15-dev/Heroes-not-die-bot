import sys
import unittest

sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from utils.activity_config import (
    DEFAULT_ACTIVITY,
    get_activity_config,
    normalize_reward_mode,
    normalize_reward_rules,
    resolve_reward_role_ids,
)


class ActivityConfigTests(unittest.TestCase):
    def test_get_activity_config_prefers_new_activity_block(self):
        settings = {
            "economy": {
                "message_xp": 7,
                "reaction_xp": 3,
                "voice_xp_per_minute": 2,
            },
            "activity": {
                "message_xp": 11,
                "reaction_xp": 4,
                "voice_xp_per_minute": 6,
                "levelup_channel_id": 123,
                "reward_mode": "stack_all",
            },
        }

        cfg = get_activity_config(settings)

        self.assertEqual(cfg["message_xp"], 11)
        self.assertEqual(cfg["reaction_xp"], 4)
        self.assertEqual(cfg["voice_xp_per_minute"], 6)
        self.assertEqual(cfg["levelup_channel_id"], 123)
        self.assertEqual(cfg["reward_mode"], "stack_all")

    def test_get_activity_config_falls_back_to_legacy_fields(self):
        settings = {
            "economy": {
                "message_xp": 8,
                "reaction_xp": 5,
                "voice_xp_per_minute": 4,
            },
            "levelup_channel_id": 987,
        }

        cfg = get_activity_config(settings)

        self.assertEqual(cfg["message_xp"], 8)
        self.assertEqual(cfg["reaction_xp"], 5)
        self.assertEqual(cfg["voice_xp_per_minute"], 4)
        self.assertEqual(cfg["levelup_channel_id"], 987)
        self.assertEqual(cfg["reward_mode"], DEFAULT_ACTIVITY["reward_mode"])

    def test_normalize_reward_rules_drops_invalid_and_duplicates(self):
        rules = normalize_reward_rules(
            [
                {"level": 10, "role_id": 1},
                {"level": 10, "role_id": 1},
                {"level": 0, "role_id": 2},
                {"level": 20, "role_id": -5},
                {"level": 15, "role_id": 3},
                {"bad": "data"},
            ]
        )

        self.assertEqual(rules, [{"level": 10, "role_id": 1}, {"level": 15, "role_id": 3}])

    def test_normalize_reward_mode_defaults_to_highest_only(self):
        self.assertEqual(normalize_reward_mode("stack_all"), "stack_all")
        self.assertEqual(normalize_reward_mode("garbage"), "highest_only")
        self.assertEqual(normalize_reward_mode(None), "highest_only")

    def test_resolve_reward_role_ids_highest_only(self):
        cfg = {
            "reward_mode": "highest_only",
            "reward_roles": [
                {"level": 5, "role_id": 100},
                {"level": 10, "role_id": 200},
                {"level": 10, "role_id": 201},
                {"level": 20, "role_id": 300},
            ],
        }
        self.assertEqual(resolve_reward_role_ids(3, cfg), set())
        self.assertEqual(resolve_reward_role_ids(7, cfg), {100})
        self.assertEqual(resolve_reward_role_ids(10, cfg), {200, 201})
        self.assertEqual(resolve_reward_role_ids(25, cfg), {300})

    def test_resolve_reward_role_ids_stack_all(self):
        cfg = {
            "reward_mode": "stack_all",
            "reward_roles": [
                {"level": 5, "role_id": 100},
                {"level": 10, "role_id": 200},
                {"level": 20, "role_id": 300},
            ],
        }
        self.assertEqual(resolve_reward_role_ids(25, cfg), {100, 200, 300})


if __name__ == "__main__":
    unittest.main()
