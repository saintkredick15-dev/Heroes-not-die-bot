import sys
import unittest


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from commands.administration.config import (  # noqa: E402
    CONFIG_SCHEMA_VERSION,
    _export_payload,
    _strip_code_block,
    _unwrap_config_payload,
    _validate_economy_patch,
    _validate_welcome_patch,
)


class ConfigHelpersTests(unittest.TestCase):
    def test_strip_code_block_removes_json_fence(self) -> None:
        raw = """```json
{"daily_amount": 300}
```"""

        self.assertEqual(_strip_code_block(raw), '{"daily_amount": 300}')

    def test_unwrap_config_payload_accepts_matching_envelope(self) -> None:
        payload = {
            "module": "economy",
            "version": CONFIG_SCHEMA_VERSION,
            "patch": {"daily_amount": 300},
        }

        self.assertEqual(_unwrap_config_payload("economy", payload), {"daily_amount": 300})

    def test_unwrap_config_payload_rejects_module_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            _unwrap_config_payload(
                "economy",
                {"module": "welcome", "version": CONFIG_SCHEMA_VERSION, "patch": {"daily_amount": 300}},
            )

    def test_unwrap_config_payload_rejects_unsupported_version(self) -> None:
        with self.assertRaises(ValueError):
            _unwrap_config_payload(
                "economy",
                {"module": "economy", "version": CONFIG_SCHEMA_VERSION + 1, "patch": {"daily_amount": 300}},
            )


class EconomyPatchValidationTests(unittest.TestCase):
    def test_validate_economy_patch_rejects_runtime_keys(self) -> None:
        with self.assertRaises(ValueError):
            _validate_economy_patch({"fund_current": 50})

    def test_validate_economy_patch_rejects_duplicate_shop_roles(self) -> None:
        with self.assertRaises(ValueError):
            _validate_economy_patch(
                {
                    "shop_roles": [
                        {"role_id": 1, "price": 10},
                        {"role_id": 1, "price": 20},
                    ]
                }
            )

    def test_validate_economy_patch_accepts_valid_transfer_tax_percent(self) -> None:
        patch = _validate_economy_patch({"transfer_tax_percent": 5})

        self.assertEqual(patch["transfer_tax_percent"], 5)

    def test_validate_economy_patch_rejects_out_of_range_transfer_tax_percent(self) -> None:
        with self.assertRaises(ValueError):
            _validate_economy_patch({"transfer_tax_percent": 51})


class WelcomePatchValidationTests(unittest.TestCase):
    def test_validate_welcome_patch_normalizes_hex_colors(self) -> None:
        patch = _validate_welcome_patch({"welcome_font_color": "ff00aa"})

        self.assertEqual(patch["welcome_font_color"], "#ff00aa")

    def test_validate_welcome_patch_rejects_invalid_hex_colors(self) -> None:
        with self.assertRaises(ValueError):
            _validate_welcome_patch({"welcome_font_color": "purple"})


class ExportPayloadTests(unittest.TestCase):
    def test_export_payload_strips_economy_runtime_keys(self) -> None:
        payload = {
            "daily_amount": 300,
            "fund_current": 123,
            "season_start": 999,
        }

        exported = _export_payload("economy", payload)

        self.assertEqual(exported, {"daily_amount": 300})

    def test_export_payload_keeps_non_economy_payloads_untouched(self) -> None:
        payload = {"welcome_channel_id": 123}

        self.assertEqual(_export_payload("welcome", payload), payload)


if __name__ == "__main__":
    unittest.main()
