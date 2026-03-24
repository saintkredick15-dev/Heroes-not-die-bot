import sys
import unittest
from types import SimpleNamespace
from unittest import mock


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from services.auction_manager import AuctionView  # noqa: E402


class AuctionProcessBidTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_bid_rejects_bid_below_start_when_no_leader(self) -> None:
        view = AuctionView(
            manager=None,
            guild_id=100,
            lot={"name": "Lot", "start_bid": 500, "duration": 60},
            eco={"currency_emoji": "coin", "auction_anti_snipe_seconds": 30},
        )
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=42),
            response=SimpleNamespace(send_message=mock.AsyncMock()),
        )

        with mock.patch("services.auction_manager.time.time", return_value=10):
            await view.process_bid(interaction, 400)

        interaction.response.send_message.assert_awaited_once()
        self.assertEqual(view.current_bid, 500)
        self.assertIsNone(view.highest_bidder)

    async def test_process_bid_updates_leader_and_extends_anti_snipe(self) -> None:
        view = AuctionView(
            manager=None,
            guild_id=100,
            lot={"name": "Lot", "start_bid": 500, "duration": 60},
            eco={"currency_emoji": "coin", "auction_anti_snipe_seconds": 30},
        )
        view.end_time = 100

        interaction = SimpleNamespace(
            user=SimpleNamespace(id=42),
            response=SimpleNamespace(send_message=mock.AsyncMock()),
        )

        fake_db = SimpleNamespace(users=SimpleNamespace(update_one=mock.AsyncMock()))
        fake_get_user = mock.AsyncMock(return_value={"bank": 200, "wallet": 900})
        fake_invalidate = mock.AsyncMock()

        with mock.patch("services.auction_manager.db", fake_db), \
             mock.patch("services.auction_manager.get_user", fake_get_user), \
             mock.patch("modules.db.invalidate_user_data", fake_invalidate), \
             mock.patch("services.auction_manager.time.time", return_value=90):
            await view.process_bid(interaction, 700)

        self.assertEqual(view.current_bid, 700)
        self.assertEqual(view.highest_bidder, 42)
        self.assertEqual(view.end_time, 130)
        fake_db.users.update_one.assert_awaited_once()
        fake_invalidate.assert_awaited_once_with(100, 42)
        interaction.response.send_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
