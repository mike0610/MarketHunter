"""
MarketHunter

Tests for ResearchMonitorService.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from models.candle import Candle
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.monitor_service import ResearchMonitorService


class MemoryRepository:
    """
    In-memory repository for monitor service tests.
    """

    def __init__(
        self,
        trades: list[ResearchTrade],
    ) -> None:
        self.trades = trades
        self.saved: list[ResearchTrade] = []

    def list_open(
        self,
    ) -> list[ResearchTrade]:
        return [
            trade
            for trade in self.trades
            if trade.is_open
        ]

    def save(
        self,
        trade: ResearchTrade,
    ) -> None:
        self.saved.append(trade)


class ResearchMonitorServiceTests(
    unittest.IsolatedAsyncioTestCase,
):
    """
    Tests one-cycle monitoring behavior.
    """

    def setUp(self) -> None:
        self.start = datetime(
            2026,
            7,
            8,
            0,
            0,
            0,
            tzinfo=timezone.utc,
        )

    def candle(
        self,
        offset: int,
        high: float,
        low: float,
        close: float,
    ) -> Candle:
        """
        Create deterministic UTC one-minute candle.
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
        created_at: datetime | None = None,
    ) -> ResearchTrade:
        """
        Create a standard waiting LONG trade.
        """

        return ResearchTrade(
            id="monitor-long",
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
            created_at=created_at or self.start,
        )

    async def test_first_cycle_uses_only_post_creation_candles(
        self,
    ) -> None:
        """
        Candles closed before or at creation time must be ignored.
        """

        trade = self.long_trade(
            created_at=self.start + timedelta(
                minutes=1,
            ),
        )

        repository = MemoryRepository(
            trades=[trade],
        )

        service = ResearchMonitorService(
            repository=repository,
        )

        historical_entry = self.candle(
            offset=0,
            high=101.0,
            low=99.0,
            close=100.0,
        )

        latest_without_entry = self.candle(
            offset=1,
            high=99.5,
            low=98.0,
            close=99.0,
        )

        async def candle_loader(
            _: ResearchTrade,
        ) -> list[Candle]:
            return [
                historical_entry,
                latest_without_entry,
            ]

        result = await service.run_once(
            candle_loader=candle_loader,
            now=self.start + timedelta(
                minutes=10,
            ),
        )

        self.assertEqual(
            result.monitored_trades,
            1,
        )

        self.assertEqual(
            result.activated,
            0,
        )

        self.assertEqual(
            trade.status,
            TradeStatus.WAITING_ENTRY,
        )

        self.assertEqual(
            trade.last_processed_candle_at,
            latest_without_entry.close_time,
        )

    async def test_trade_activates_then_closes_at_tp(
        self,
    ) -> None:
        """
        Waiting trade activates first, then closes on later TP candle.
        """

        trade = self.long_trade(
            created_at=self.start - timedelta(
                minutes=1,
            ),
        )

        repository = MemoryRepository(
            trades=[trade],
        )

        service = ResearchMonitorService(
            repository=repository,
        )

        entry_candle = self.candle(
            offset=0,
            high=101.0,
            low=99.0,
            close=100.0,
        )

        async def entry_loader(
            _: ResearchTrade,
        ) -> list[Candle]:
            return [entry_candle]

        first_result = await service.run_once(
            candle_loader=entry_loader,
            now=self.start + timedelta(
                minutes=10,
            ),
        )

        self.assertEqual(
            first_result.activated,
            1,
        )

        self.assertEqual(
            trade.status,
            TradeStatus.ACTIVE,
        )

        take_profit_candle = self.candle(
            offset=1,
            high=111.0,
            low=99.0,
            close=110.0,
        )

        async def tp_loader(
            _: ResearchTrade,
        ) -> list[Candle]:
            return [
                entry_candle,
                take_profit_candle,
            ]

        second_result = await service.run_once(
            candle_loader=tp_loader,
            now=self.start + timedelta(
                minutes=10,
            ),
        )

        self.assertEqual(
            second_result.closed_tp,
            1,
        )

        self.assertEqual(
            trade.status,
            TradeStatus.CLOSED,
        )

        self.assertEqual(
            trade.close_reason,
            "TP",
        )

        self.assertAlmostEqual(
            trade.profit_percent,
            10.0,
        )

    async def test_unfinished_candle_is_not_processed(
        self,
    ) -> None:
        """
        Current unfinished exchange candle must be ignored.
        """

        trade = self.long_trade()

        repository = MemoryRepository(
            trades=[trade],
        )

        service = ResearchMonitorService(
            repository=repository,
        )

        unfinished = self.candle(
            offset=10,
            high=101.0,
            low=99.0,
            close=100.0,
        )

        async def candle_loader(
            _: ResearchTrade,
        ) -> list[Candle]:
            return [unfinished]

        result = await service.run_once(
            candle_loader=candle_loader,
            now=self.start + timedelta(
                minutes=5,
            ),
        )

        self.assertEqual(
            result.monitored_trades,
            0,
        )

        self.assertEqual(
            result.skipped_without_candles,
            1,
        )

        self.assertEqual(
            trade.status,
            TradeStatus.WAITING_ENTRY,
        )


if __name__ == "__main__":
    unittest.main()