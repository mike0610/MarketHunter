"""
MarketHunter

Tests for TradeMonitor lifecycle rules.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from models.candle import Candle
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.monitor import TradeMonitor


class MemoryRepository:
    """
    Minimal repository substitute for TradeMonitor tests.
    """

    def __init__(self) -> None:
        self.saved: list[ResearchTrade] = []

    def save(
        self,
        trade: ResearchTrade,
    ) -> None:
        self.saved.append(trade)


class TradeMonitorTests(unittest.TestCase):
    """
    Tests virtual trade activation, TP, SL and expiry behavior.
    """

    def setUp(self) -> None:
        self.repository = MemoryRepository()
        self.monitor = TradeMonitor(
            repository=self.repository,
        )

        self.start = datetime(
            2026,
            7,
            8,
            0,
            0,
            0,
        )

    def candle(
        self,
        offset: int,
        high: float,
        low: float,
        close: float,
    ) -> Candle:
        """
        Create deterministic test candle.
        """

        open_time = self.start + timedelta(
            minutes=offset,
        )

        close_time = open_time + timedelta(
            minutes=1,
        )

        return Candle(
            open_time=open_time,
            open=100.0,
            high=high,
            low=low,
            close=close,
            volume=1_000.0,
            close_time=close_time,
            quote_volume=100_000.0,
            trades=100,
            taker_buy_base_volume=500.0,
            taker_buy_quote_volume=50_000.0,
        )

    def long_trade(
        self,
        max_active_candles: int = 30,
    ) -> ResearchTrade:
        """
        Create a standard LONG research trade.
        """

        return ResearchTrade(
            id="long-trade",
            signal_id=None,
            symbol="BTCUSDT",
            market="futures",
            timeframe="1m",
            strategy="TestStrategy",
            direction="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            probability=45,
            score=80.0,
            max_active_candles=max_active_candles,
        )

    def short_trade(self) -> ResearchTrade:
        """
        Create a standard SHORT research trade.
        """

        return ResearchTrade(
            id="short-trade",
            signal_id=None,
            symbol="ETHUSDT",
            market="futures",
            timeframe="1m",
            strategy="TestStrategy",
            direction="SHORT",
            entry_price=100.0,
            stop_loss=105.0,
            take_profit=90.0,
            probability=45,
            score=80.0,
        )

    def test_entry_candle_activates_without_tp_sl_check(
        self,
    ) -> None:
        """
        Entry candle activates trade but does not close it.
        """

        trade = self.long_trade()

        candle = self.candle(
            offset=0,
            high=112.0,
            low=94.0,
            close=105.0,
        )

        result = self.monitor.update_with_candle(
            trade=trade,
            candle=candle,
        )

        self.assertEqual(
            result.status,
            TradeStatus.ACTIVE,
        )
        self.assertEqual(
            result.active_candles,
            0,
        )
        self.assertIsNone(
            result.close_reason,
        )

    def test_same_candle_is_not_processed_twice(
        self,
    ) -> None:
        """
        Duplicate candle must not advance active candle counter.
        """

        trade = self.long_trade()

        candle = self.candle(
            offset=0,
            high=101.0,
            low=99.0,
            close=100.0,
        )

        self.monitor.update_with_candle(
            trade=trade,
            candle=candle,
        )

        self.monitor.update_with_candle(
            trade=trade,
            candle=candle,
        )

        self.assertEqual(
            trade.active_candles,
            0,
        )
        self.assertEqual(
            trade.status,
            TradeStatus.ACTIVE,
        )

    def test_long_both_tp_and_sl_uses_conservative_sl(
        self,
    ) -> None:
        """
        When both levels are touched in one candle, SL wins.
        """

        trade = self.long_trade()

        self.monitor.update_with_candle(
            trade=trade,
            candle=self.candle(
                offset=0,
                high=101.0,
                low=99.0,
                close=100.0,
            ),
        )

        result = self.monitor.update_with_candle(
            trade=trade,
            candle=self.candle(
                offset=1,
                high=112.0,
                low=94.0,
                close=100.0,
            ),
        )

        self.assertEqual(
            result.status,
            TradeStatus.CLOSED,
        )
        self.assertEqual(
            result.close_reason,
            "SL",
        )
        self.assertAlmostEqual(
            result.profit_percent,
            -5.0,
        )
        self.assertAlmostEqual(
            result.rr,
            -1.0,
        )

    def test_short_trade_closes_at_take_profit(
        self,
    ) -> None:
        """
        SHORT trade closes at TP when low reaches target.
        """

        trade = self.short_trade()

        self.monitor.update_with_candle(
            trade=trade,
            candle=self.candle(
                offset=0,
                high=101.0,
                low=99.0,
                close=100.0,
            ),
        )

        result = self.monitor.update_with_candle(
            trade=trade,
            candle=self.candle(
                offset=1,
                high=102.0,
                low=89.0,
                close=91.0,
            ),
        )

        self.assertEqual(
            result.status,
            TradeStatus.CLOSED,
        )
        self.assertEqual(
            result.close_reason,
            "TP",
        )
        self.assertAlmostEqual(
            result.profit_percent,
            10.0,
        )
        self.assertAlmostEqual(
            result.rr,
            2.0,
        )

    def test_trade_expires_after_max_active_candles(
        self,
    ) -> None:
        """
        Trade expires after configured active candle limit.
        """

        trade = self.long_trade(
            max_active_candles=2,
        )

        self.monitor.update_with_candle(
            trade=trade,
            candle=self.candle(
                offset=0,
                high=101.0,
                low=99.0,
                close=100.0,
            ),
        )

        self.monitor.update_with_candle(
            trade=trade,
            candle=self.candle(
                offset=1,
                high=103.0,
                low=98.0,
                close=101.0,
            ),
        )

        result = self.monitor.update_with_candle(
            trade=trade,
            candle=self.candle(
                offset=2,
                high=104.0,
                low=98.0,
                close=102.0,
            ),
        )

        self.assertEqual(
            result.status,
            TradeStatus.EXPIRED,
        )
        self.assertEqual(
            result.close_reason,
            "EXPIRED",
        )
        self.assertEqual(
            result.active_candles,
            2,
        )


if __name__ == "__main__":
    unittest.main()