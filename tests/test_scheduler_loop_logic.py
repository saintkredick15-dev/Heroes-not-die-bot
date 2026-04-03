import sys
import unittest
from types import SimpleNamespace
from unittest import mock


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from services.scheduler import SchedulerCog  # noqa: E402


class _FakeUsersCollection:
    def __init__(self):
        self.update_many = mock.AsyncMock()


class _AsyncIter:
    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class _FakeGuildSettingsCollection:
    def __init__(self, docs):
        self._docs = docs
        self.update_one = mock.AsyncMock()

    def find(self, _query):
        return _AsyncIter(self._docs)


class SchedulerLoopLogicTests(unittest.IsolatedAsyncioTestCase):
    async def test_season_reset_does_not_skip_weekly_and_monthly_resets(self) -> None:
        fake_users = _FakeUsersCollection()
        fake_guild_settings = _FakeGuildSettingsCollection(
            [
                {
                    "_id": 777,
                    "economy": {
                        "enabled": True,
                        "season_duration_days": 30,
                        "season_start": 1_700_000_000,
                    },
                    "scheduler_state": {},
                }
            ]
        )
        fake_db = SimpleNamespace(users=fake_users, guild_settings=fake_guild_settings)
        fake_bot = SimpleNamespace(guilds=[])

        with mock.patch("services.scheduler.db", fake_db), \
             mock.patch.object(SchedulerCog, "trigger_season_end", new=mock.AsyncMock()) as trigger_mock, \
             mock.patch("services.scheduler.time.time", return_value=1_704_067_200):
            cog = SchedulerCog.__new__(SchedulerCog)
            cog.bot = fake_bot
            await SchedulerCog.economy_scheduler.coro(cog)

        trigger_mock.assert_awaited_once()
        self.assertEqual(fake_users.update_many.await_count, 2)

        weekly_payload = fake_users.update_many.await_args_list[0].args[1]["$set"]
        monthly_payload = fake_users.update_many.await_args_list[1].args[1]["$set"]

        self.assertEqual(weekly_payload["messages_week"], 0)
        self.assertEqual(weekly_payload["voice_minutes_week"], 0)
        self.assertEqual(weekly_payload["reactions_week"], 0)
        self.assertEqual(monthly_payload["messages_month"], 0)
        self.assertEqual(monthly_payload["voice_minutes_month"], 0)
        self.assertEqual(monthly_payload["reactions_month"], 0)


if __name__ == "__main__":
    unittest.main()
