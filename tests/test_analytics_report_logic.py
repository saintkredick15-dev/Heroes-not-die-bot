import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from events.analytics import _build_stats_embed  # noqa: E402


class AnalyticsReportRenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_stats_embed_includes_new_sections_and_lifetime_metric(self) -> None:
        fake_guild = SimpleNamespace(
            id=123,
            name="hrs dev",
            member_count=42,
            icon=SimpleNamespace(url="https://example.com/icon.png"),
        )

        with mock.patch(
            "events.analytics.aggregate_guild_analytics",
            new=mock.AsyncMock(
                return_value={
                    "messages": 12,
                    "reactions": 5,
                    "voice_minutes": 180,
                    "joins": 4,
                    "leaves": 1,
                    "net_members": 3,
                    "tickets_opened": 2,
                    "tickets_closed": 1,
                    "warns": 6,
                    "mutes": 2,
                    "bans": 1,
                    "unbans": 1,
                    "mod_actions_total": 10,
                    "economy_given": 500,
                }
            ),
        ), mock.patch(
            "events.analytics.aggregate_guild_analytics_lifetime",
            new=mock.AsyncMock(return_value={"leaves": 9}),
        ), mock.patch(
            "events.analytics.datetime"
        ) as datetime_mock:
            current = datetime(2026, 4, 7, 15, 0, tzinfo=timezone.utc)
            datetime_mock.now.return_value = current

            embed = await _build_stats_embed(fake_guild, 7)

        self.assertIn("Статистика сервера за 7 днів", embed.title)
        self.assertIn("Тікети: **2/1**", embed.description)
        self.assertIn("Період", embed.fields[0].name)
        self.assertIn("Наступний звіт", embed.fields[1].name)
        members_field = next(field for field in embed.fields if field.name.endswith("Учасники"))
        self.assertIn("Якби ніхто не пішов: **51**", members_field.value)
        moderation_field = next(field for field in embed.fields if field.name.endswith("Модерація"))
        self.assertIn("Всього дій: **10**", moderation_field.value)
        tickets_field = next(field for field in embed.fields if field.name.endswith("Tickets"))
        self.assertIn("Відкрито: **2**", tickets_field.value)
        self.assertIn("Закрито: **1**", tickets_field.value)


if __name__ == "__main__":
    unittest.main()
