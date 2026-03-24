import sys
import unittest
from types import SimpleNamespace
from unittest import mock


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from services.scheduler import perform_season_reset  # noqa: E402


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, length=None):
        return list(self._rows)


class _FakeCollection:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.update_many = mock.AsyncMock()
        self.update_one = mock.AsyncMock()

    def find(self, _query):
        return _FakeCursor(self._rows)


class _FakeRole:
    def __init__(self):
        self.members = []


class _FakeGuild:
    def __init__(self, guild_id: int):
        self.id = guild_id

    def get_member(self, user_id: int):
        return SimpleNamespace(id=user_id, mention=f"<@{user_id}>")

    def get_role(self, _role_id: int):
        return _FakeRole()

    def get_channel(self, _channel_id: int):
        return None


class PerformSeasonResetTests(unittest.IsolatedAsyncioTestCase):
    async def test_perform_season_reset_updates_history_and_resets_balances(self) -> None:
        fake_users = _FakeCollection(
            rows=[
                {"user_id": 1, "wallet": 500, "bank": 500},
                {"user_id": 2, "wallet": 700, "bank": 0},
                {"user_id": 3, "wallet": 100, "bank": 50},
                {"user_id": 4, "wallet": 0, "bank": 0},
            ]
        )
        fake_guild_settings = _FakeCollection()
        fake_db = SimpleNamespace(users=fake_users, guild_settings=fake_guild_settings)
        guild = _FakeGuild(555)
        eco = {
            "season_number": 4,
            "currency_emoji": "coin",
            "currency_name": "Coin",
            "season_start_bonus": 100,
            "season_winner_roles": {},
            "season_announce_channel_id": 0,
        }
        gd = {"season_history": []}

        with mock.patch("services.scheduler.db", fake_db), \
             mock.patch("services.scheduler.time.time", return_value=1_700_000_000):
            await perform_season_reset(guild, eco=eco, gd=gd)

        fake_users.update_many.assert_awaited_once()
        reset_payload = fake_users.update_many.await_args.args[1]["$set"]
        self.assertEqual(reset_payload["wallet"], 100)
        self.assertEqual(reset_payload["bank"], 0)
        self.assertEqual(reset_payload["eco_history"], [])

        fake_guild_settings.update_one.assert_awaited_once()
        stored = fake_guild_settings.update_one.await_args.args[1]["$set"]
        self.assertEqual(stored["economy"]["season_number"], 5)
        self.assertEqual(stored["economy"]["season_start"], 1_700_000_000)
        self.assertEqual(stored["season_history"][-1]["season"], 4)
        self.assertEqual(
            stored["season_history"][-1]["top3"],
            [
                {"user_id": 1, "earned": 1000},
                {"user_id": 2, "earned": 700},
                {"user_id": 3, "earned": 150},
            ],
        )


if __name__ == "__main__":
    unittest.main()
