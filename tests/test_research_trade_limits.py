"""
MarketHunter

Tests for virtual research trade limits.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from models.signal import Signal
from pipeline.handlers import ResearchTradeHandler
from research.manager import ResearchManager
from research.storage.repository import ResearchRepository


class ResearchTradeLimitTests(unittest.TestCase):
    """
    Test global, per-symbol and duplicate-direction limits.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

        database_path = Path(
            self.temp_dir.name
        ) / "research.db"

        self.repository = ResearchRepository(
            path=str(database_path),
        )

    def tearDown(self) -> None:
        self.repository.close()
        self.temp_dir.cleanup()

    @staticmethod
    def signal(
        symbol: str,
        strategy: str,
        direction: str = "LONG",
        market: str = "futures",
    ) -> Signal:
        """
        Create a deterministic virtual signal.
        """

        return Signal(
            symbol=symbol,
            market=market,
            timeframe="1h",
            strategy=strategy,
            direction=direction,
            score=75.0,
        )

    def test_same_direction_is_blocked_across_strategies(
        self,
    ) -> None:
        """
        FVG and OrderBlock cannot create duplicate LONG positions.
        """

        manager = ResearchManager(
            repository=self.repository,
            max_open_trades=10,
            max_open_trades_per_symbol=2,
        )

        first = manager.create_from_signal(
            signal=self.signal(
                symbol="BTCUSDT",
                strategy="FVG",
            ),
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            probability=50,
        )

        second = manager.create_from_signal(
            signal=self.signal(
                symbol="BTCUSDT",
                strategy="OrderBlock",
            ),
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            probability=50,
        )

        self.assertTrue(
            first.created,
        )

        self.assertFalse(
            second.created,
        )

        self.assertIn(
            "already exists",
            second.reason or "",
        )

        self.assertEqual(
            len(self.repository.list_open()),
            1,
        )

    def test_per_symbol_limit_blocks_opposite_direction(
        self,
    ) -> None:
        """
        A symbol cap of one blocks a conflicting SHORT trade too.
        """

        manager = ResearchManager(
            repository=self.repository,
            max_open_trades=10,
            max_open_trades_per_symbol=1,
        )

        first = manager.create_from_signal(
            signal=self.signal(
                symbol="ETHUSDT",
                strategy="Breakout",
                direction="LONG",
            ),
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            probability=50,
        )

        second = manager.create_from_signal(
            signal=self.signal(
                symbol="ETHUSDT",
                strategy="FalseBreakout",
                direction="SHORT",
            ),
            entry_price=100.0,
            stop_loss=105.0,
            take_profit=90.0,
            probability=50,
        )

        self.assertTrue(
            first.created,
        )

        self.assertFalse(
            second.created,
        )

        self.assertIn(
            "limit for ETHUSDT",
            second.reason or "",
        )

    def test_global_open_trade_limit_is_enforced(
        self,
    ) -> None:
        """
        No new trade is created after global maximum is reached.
        """

        manager = ResearchManager(
            repository=self.repository,
            max_open_trades=2,
            max_open_trades_per_symbol=1,
        )

        for symbol in [
            "BTCUSDT",
            "ETHUSDT",
        ]:
            result = manager.create_from_signal(
                signal=self.signal(
                    symbol=symbol,
                    strategy="Breakout",
                ),
                entry_price=100.0,
                stop_loss=95.0,
                take_profit=110.0,
                probability=50,
            )

            self.assertTrue(
                result.created,
            )

        blocked = manager.create_from_signal(
            signal=self.signal(
                symbol="SOLUSDT",
                strategy="Breakout",
            ),
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            probability=50,
        )

        self.assertFalse(
            blocked.created,
        )

        self.assertIn(
            "Global open virtual trade limit",
            blocked.reason or "",
        )

        self.assertEqual(
            self.repository.count_open_trades(),
            2,
        )

    def test_spot_long_is_accepted(
        self,
    ) -> None:
        """
        SPOT market allows a LONG virtual trade.
        """

        manager = ResearchManager(
            repository=self.repository,
            max_open_trades=10,
            max_open_trades_per_symbol=1,
        )

        result = manager.create_from_signal(
            signal=self.signal(
                symbol="BTCUSDT",
                strategy="PremiumDiscount",
                direction="LONG",
                market="spot",
            ),
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            probability=50,
        )

        self.assertTrue(
            result.created,
        )

        self.assertEqual(
            self.repository.count_open_trades(),
            1,
        )

    def test_spot_short_is_rejected(
        self,
    ) -> None:
        """
        SPOT market does not support SHORT virtual trades.
        """

        manager = ResearchManager(
            repository=self.repository,
            max_open_trades=10,
            max_open_trades_per_symbol=1,
        )

        result = manager.create_from_signal(
            signal=self.signal(
                symbol="BTCUSDT",
                strategy="PremiumDiscount",
                direction="SHORT",
                market="spot",
            ),
            entry_price=100.0,
            stop_loss=105.0,
            take_profit=90.0,
            probability=50,
        )

        self.assertFalse(
            result.created,
        )

        self.assertEqual(
            result.reason,
            "spot_short_not_supported",
        )

        self.assertEqual(
            self.repository.count_open_trades(),
            0,
        )

    def test_futures_short_is_accepted(
        self,
    ) -> None:
        """
        FUTURES market continues to allow SHORT virtual trades.
        """

        manager = ResearchManager(
            repository=self.repository,
            max_open_trades=10,
            max_open_trades_per_symbol=1,
        )

        result = manager.create_from_signal(
            signal=self.signal(
                symbol="BTCUSDT",
                strategy="PremiumDiscount",
                direction="SHORT",
                market="futures",
            ),
            entry_price=100.0,
            stop_loss=105.0,
            take_profit=90.0,
            probability=50,
        )

        self.assertTrue(
            result.created,
        )

        self.assertEqual(
            self.repository.count_open_trades(),
            1,
        )


class ResearchTradeCycleLimitTests(
    unittest.IsolatedAsyncioTestCase,
):
    """
    Test research trade creation cap for one scan cycle.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

        database_path = Path(
            self.temp_dir.name
        ) / "research.db"

        self.repository = ResearchRepository(
            path=str(database_path),
        )

    def tearDown(self) -> None:
        self.repository.close()
        self.temp_dir.cleanup()

    @staticmethod
    def context(
        symbol: str,
    ) -> SimpleNamespace:
        """
        Create minimum context required by ResearchTradeHandler.
        """

        signal = Signal(
            symbol=symbol,
            market="futures",
            timeframe="1h",
            strategy="TestStrategy",
            direction="LONG",
            score=75.0,
        )

        return SimpleNamespace(
            signal=signal,
            probability=SimpleNamespace(
                probability=50,
            ),
            risk=SimpleNamespace(
                entry=100.0,
                stop_loss=95.0,
                take_profit=110.0,
            ),
            metadata={},
            research_trade=None,
        )

    async def test_cycle_limit_blocks_excess_candidates(
        self,
    ) -> None:
        """
        Only configured count of new virtual trades is created per cycle.
        """

        manager = ResearchManager(
            repository=self.repository,
            max_open_trades=10,
            max_open_trades_per_symbol=1,
        )

        handler = ResearchTradeHandler(
            manager=manager,
            minimum_probability=40,
            notional=100.0,
            maximum_new_trades_per_cycle=2,
        )

        first = self.context(
            symbol="BTCUSDT",
        )

        second = self.context(
            symbol="ETHUSDT",
        )

        third = self.context(
            symbol="SOLUSDT",
        )

        await handler.handle(first)
        await handler.handle(second)
        await handler.handle(third)

        self.assertIsNotNone(
            first.research_trade,
        )

        self.assertIsNotNone(
            second.research_trade,
        )

        self.assertIsNone(
            third.research_trade,
        )

        self.assertIn(
            "Research cycle limit reached",
            third.metadata.get(
                "research_skipped",
                "",
            ),
        )

        self.assertEqual(
            self.repository.count_open_trades(),
            2,
        )


if __name__ == "__main__":
    unittest.main()