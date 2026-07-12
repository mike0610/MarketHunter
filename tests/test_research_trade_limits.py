"""
MarketHunter

Tests for virtual research trade limits.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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


class ResearchTradeRiskGeometryGuardTests(unittest.TestCase):
    """
    Test the write-boundary risk-geometry guard in
    ResearchManager.create_from_signal().

    This guard is a last line of defense: even if a signal somehow
    bypasses the RiskGeometryDetector check in pipeline/handlers.py,
    ResearchManager itself must refuse to persist a trade with zero
    or wrong-side risk geometry.
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

    def test_valid_long_is_created(
        self,
    ) -> None:
        """
        A LONG trade with stop_loss below entry_price is created.
        """

        manager = ResearchManager(
            repository=self.repository,
        )

        result = manager.create_from_signal(
            signal=self.signal(
                symbol="BTCUSDT",
                strategy="FVG",
                direction="LONG",
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

    def test_valid_short_is_created(
        self,
    ) -> None:
        """
        A SHORT trade with stop_loss above entry_price is created.
        """

        manager = ResearchManager(
            repository=self.repository,
        )

        result = manager.create_from_signal(
            signal=self.signal(
                symbol="BTCUSDT",
                strategy="FVG",
                direction="SHORT",
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

    def test_long_entry_equals_stop_is_rejected(
        self,
    ) -> None:
        """
        A LONG trade with entry_price == stop_loss is rejected.

        Reproduces the real ARBUSDT case (entry=0.08696,
        stop_loss=0.08696) found during the baseline clean
        statistics review.
        """

        manager = ResearchManager(
            repository=self.repository,
        )

        result = manager.create_from_signal(
            signal=self.signal(
                symbol="ARBUSDT",
                strategy="FVG",
                direction="LONG",
            ),
            entry_price=0.08696,
            stop_loss=0.08696,
            take_profit=0.10414,
            probability=50,
        )

        self.assertFalse(
            result.created,
        )

        self.assertIn(
            "risk geometry",
            (result.reason or "").lower(),
        )

        self.assertEqual(
            self.repository.count_open_trades(),
            0,
        )

    def test_short_entry_equals_stop_is_rejected(
        self,
    ) -> None:
        """
        A SHORT trade with entry_price == stop_loss is rejected.
        """

        manager = ResearchManager(
            repository=self.repository,
        )

        result = manager.create_from_signal(
            signal=self.signal(
                symbol="ETHUSDT",
                strategy="FVG",
                direction="SHORT",
            ),
            entry_price=100.0,
            stop_loss=100.0,
            take_profit=90.0,
            probability=50,
        )

        self.assertFalse(
            result.created,
        )

        self.assertIn(
            "risk geometry",
            (result.reason or "").lower(),
        )

        self.assertEqual(
            self.repository.count_open_trades(),
            0,
        )

    def test_long_stop_above_entry_is_rejected(
        self,
    ) -> None:
        """
        A LONG trade with stop_loss above entry_price (wrong side)
        is rejected.
        """

        manager = ResearchManager(
            repository=self.repository,
        )

        result = manager.create_from_signal(
            signal=self.signal(
                symbol="SOLUSDT",
                strategy="FVG",
                direction="LONG",
            ),
            entry_price=100.0,
            stop_loss=105.0,
            take_profit=110.0,
            probability=50,
        )

        self.assertFalse(
            result.created,
        )

        self.assertIn(
            "risk geometry",
            (result.reason or "").lower(),
        )

        self.assertEqual(
            self.repository.count_open_trades(),
            0,
        )

    def test_short_stop_below_entry_is_rejected(
        self,
    ) -> None:
        """
        A SHORT trade with stop_loss below entry_price (wrong side)
        is rejected.
        """

        manager = ResearchManager(
            repository=self.repository,
        )

        result = manager.create_from_signal(
            signal=self.signal(
                symbol="XRPUSDT",
                strategy="FVG",
                direction="SHORT",
            ),
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=90.0,
            probability=50,
        )

        self.assertFalse(
            result.created,
        )

        self.assertIn(
            "risk geometry",
            (result.reason or "").lower(),
        )

        self.assertEqual(
            self.repository.count_open_trades(),
            0,
        )

    def test_rejected_trade_does_not_call_repository_save(
        self,
    ) -> None:
        """
        The guard rejects before repository.save() is ever invoked.
        """

        manager = ResearchManager(
            repository=self.repository,
        )

        with mock.patch.object(
            self.repository,
            "save",
        ) as mock_save:
            result = manager.create_from_signal(
                signal=self.signal(
                    symbol="ARBUSDT",
                    strategy="FVG",
                    direction="LONG",
                ),
                entry_price=0.08696,
                stop_loss=0.08696,
                take_profit=0.10414,
                probability=50,
            )

        self.assertFalse(
            result.created,
        )

        mock_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()