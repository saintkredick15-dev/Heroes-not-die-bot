import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from events.stats import BotStats  # noqa: E402
from services.stats_contract import (  # noqa: E402
    aggregate_guild_analytics,
    aggregate_guild_analytics_lifetime,
    analytics_window_start,
    build_site_stats_snapshot,
)


class _FakeAggregateCursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._index]
        self._index += 1
        return item


class _FakeAnalyticsCollection:
    def __init__(self, docs):
        self._docs = docs
        self.pipeline = None

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return _FakeAggregateCursor(self._docs)


class StatsContractTests(unittest.IsolatedAsyncioTestCase):
    def test_window_start_uses_inclusive_utc_day_buckets(self) -> None:
        now = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(analytics_window_start(1, now), "2026-04-01")
        self.assertEqual(analytics_window_start(7, now), "2026-03-26")
        self.assertEqual(analytics_window_start(30, now), "2026-03-03")

    async def test_aggregate_guild_analytics_normalizes_missing_fields(self) -> None:
        collection = _FakeAnalyticsCollection(
            [{"messages": 12, "voice_minutes": 180, "joins": 4, "leaves": 1, "bans": 2}]
        )
        now = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)

        result = await aggregate_guild_analytics(555, 7, collection=collection, now=now)

        self.assertEqual(collection.pipeline[0]["$match"]["date"]["$gte"], "2026-03-26")
        self.assertEqual(result["messages"], 12)
        self.assertEqual(result["voice_minutes"], 180)
        self.assertEqual(result["joins"], 4)
        self.assertEqual(result["leaves"], 1)
        self.assertEqual(result["net_members"], 3)
        self.assertEqual(result["bans"], 2)
        self.assertEqual(result["warns"], 0)
        self.assertEqual(result["economy_given"], 0)
        self.assertEqual(result["mod_actions_total"], 2)
        self.assertEqual(result["tickets_opened"], 0)
        self.assertEqual(result["tickets_closed"], 0)

    async def test_aggregate_guild_analytics_lifetime_sums_all_documents(self) -> None:
        collection = _FakeAnalyticsCollection(
            [{"messages": 7, "leaves": 4, "tickets_opened": 4, "tickets_closed": 2}]
        )

        result = await aggregate_guild_analytics_lifetime(555, collection=collection)

        self.assertEqual(collection.pipeline[0]["$match"], {"guild_id": 555})
        self.assertEqual(result["messages"], 7)
        self.assertEqual(result["leaves"], 4)
        self.assertEqual(result["tickets_opened"], 4)
        self.assertEqual(result["tickets_closed"], 2)

    def test_build_site_stats_snapshot_uses_stable_shape(self) -> None:
        now = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)
        snapshot = build_site_stats_snapshot(
            guild_id=777,
            guild_name="hrs dev",
            member_count=42,
            icon_url="https://example.com/icon.png",
            stats_24h={"messages": 5},
            stats_7d={"messages": 10},
            stats_30d={"messages": 20},
            now=now,
        )

        self.assertEqual(snapshot["guild_id"], "777")
        self.assertEqual(snapshot["name"], "hrs dev")
        self.assertEqual(snapshot["member_count"], 42)
        self.assertEqual(snapshot["icon"], "https://example.com/icon.png")
        self.assertEqual(snapshot["stats_24h"], {"messages": 5})
        self.assertEqual(snapshot["stats_7d"], {"messages": 10})
        self.assertEqual(snapshot["stats_30d"], {"messages": 20})
        self.assertEqual(snapshot["last_updated"], now)

    async def test_bot_stats_logic_builds_site_snapshot_from_canonical_analytics(self) -> None:
        fake_site_stats = SimpleNamespace(update_one=mock.AsyncMock())
        fake_db = SimpleNamespace(site_stats=fake_site_stats, guild_analytics=object())
        fake_guild = SimpleNamespace(
            id=123,
            name="Vangard",
            member_count=7,
            icon=SimpleNamespace(url="https://example.com/icon.png"),
        )
        fake_bot = SimpleNamespace(guilds=[fake_guild])

        with mock.patch("events.stats.db", fake_db), \
             mock.patch("events.stats.aggregate_guild_analytics", new=mock.AsyncMock(side_effect=[
                 {"messages": 1},
                 {"messages": 7},
                 {"messages": 30},
             ])):
            cog = BotStats.__new__(BotStats)
            cog.bot = fake_bot
            await BotStats.update_stats_logic(cog)

        self.assertEqual(fake_site_stats.update_one.await_count, 2)
        general_update = fake_site_stats.update_one.await_args_list[0]
        guild_update = fake_site_stats.update_one.await_args_list[1]

        self.assertEqual(general_update.args[0], {"_id": "general_stats"})
        self.assertEqual(general_update.args[1]["$set"]["server_count"], 1)
        self.assertEqual(general_update.args[1]["$set"]["member_count"], 7)

        self.assertEqual(guild_update.args[0], {"_id": "123"})
        set_payload = guild_update.args[1]["$set"]
        unset_payload = guild_update.args[1]["$unset"]
        self.assertEqual(set_payload["guild_id"], "123")
        self.assertEqual(set_payload["stats_24h"], {"messages": 1})
        self.assertEqual(set_payload["stats_7d"], {"messages": 7})
        self.assertEqual(set_payload["stats_30d"], {"messages": 30})
        self.assertEqual(unset_payload["messages_24h"], "")
        self.assertEqual(unset_payload["mod_actions_24h"], "")


if __name__ == "__main__":
    unittest.main()
