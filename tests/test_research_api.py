"""
MarketHunter

Tests for Research API endpoints.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import api.research_api as research_api
from api.app import app
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.storage.repository import ResearchRepository


class ResearchApiTests(unittest.TestCase):
    """
    Test virtual trade API responses.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

        self.database_path = Path(
            self.temp_dir.name
        ) / "research.db"

        self.previous_database_path = (
            research_api.DATABASE_PATH
        )

        research_api.DATABASE_PATH = str(
            self.database_path
        )

        self.repository = ResearchRepository(
            path=str(self.database_path),
        )

        self._seed_trades()

        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.repository.close()

        research_api.DATABASE_PATH = (
            self.previous_database_path
        )

        self.temp_dir.cleanup()

    def _seed_trades(self) -> None:
        """
        Insert deterministic waiting and active trades.
        """

        created_at = datetime(
            2026,
            7,
            8,
            12,
            0,
            0,
            tzinfo=timezone.utc,
        )

        waiting_trade = ResearchTrade(
            id="waiting-btc",
            signal_id=None,
            symbol="BTCUSDT",
            market="futures",
            timeframe="1h",
            strategy="FVG",
            direction="LONG",
            entry_price=100_000.0,
            stop_loss=98_000.0,
            take_profit=104_000.0,
            probability=55,
            score=75.0,
            created_at=created_at,
        )

        active_trade = ResearchTrade(
            id="active-eth",
            signal_id=None,
            symbol="ETHUSDT",
            market="futures",
            timeframe="1h",
            strategy="OrderBlock",
            direction="LONG",
            entry_price=3_000.0,
            stop_loss=2_900.0,
            take_profit=3_200.0,
            probability=60,
            score=80.0,
            status=TradeStatus.ACTIVE,
            created_at=created_at,
            opened_at=created_at,
        )

        self.repository.save(waiting_trade)
        self.repository.save(active_trade)

    def test_list_trades_returns_saved_trades(
        self,
    ) -> None:
        """
        API returns both saved virtual trades.

        Both fixtures have identical created_at values, so SQLite does
        not guarantee their relative ordering. The endpoint must return
        both records regardless of that order.
        """

        response = self.client.get(
            "/research/trades",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["total"],
            2,
        )

        self.assertEqual(
            len(payload["trades"]),
            2,
        )

        returned_ids = {
            trade["id"]
            for trade in payload["trades"]
        }

        self.assertEqual(
            returned_ids,
            {
                "waiting-btc",
                "active-eth",
            },
        )

    def test_list_trades_filters_by_status(
        self,
    ) -> None:
        """
        API filters virtual trades by lifecycle status.
        """

        response = self.client.get(
            "/research/trades?status=waiting_entry",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["total"],
            1,
        )

        self.assertEqual(
            payload["trades"][0]["id"],
            "waiting-btc",
        )

    def test_trade_details_returns_one_trade(
        self,
    ) -> None:
        """
        API returns full data for requested trade ID.
        """

        response = self.client.get(
            "/research/trades/active-eth",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["symbol"],
            "ETHUSDT",
        )

        self.assertEqual(
            payload["status"],
            "active",
        )

    def test_trade_details_returns_404_for_unknown_id(
        self,
    ) -> None:
        """
        API reports missing trade with HTTP 404.
        """

        response = self.client.get(
            "/research/trades/unknown-id",
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_statistics_returns_current_counts(
        self,
    ) -> None:
        """
        API returns aggregate waiting and active counters.
        """

        response = self.client.get(
            "/research/statistics",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["total"],
            2,
        )

        self.assertEqual(
            payload["waiting_entry"],
            1,
        )

        self.assertEqual(
            payload["active"],
            1,
        )


if __name__ == "__main__":
    unittest.main()