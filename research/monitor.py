"""
MarketHunter

Module:
Trade Monitor

Responsibilities:
- Activate virtual trades after entry is touched.
- Track favorable and adverse price movement.
- Close virtual trades by TP, SL or expiry.
- Prevent duplicate processing of the same candle.
"""

from __future__ import annotations

from datetime import datetime

from models.candle import Candle
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.storage.repository import ResearchRepository


class TradeMonitor:
    """
    Updates ResearchTrade records using completed market candles.

    Conservative rule:
    when one candle reaches both TP and SL, Stop Loss is considered
    to trigger first. This avoids optimistic backtest bias.
    """

    def __init__(
        self,
        repository: ResearchRepository,
    ) -> None:
        self.repository = repository

    def update_with_candle(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> ResearchTrade:
        """
        Process one completed candle for a single virtual trade.
        """

        if not trade.is_open:
            return trade

        if self._already_processed(
            trade=trade,
            candle_time=candle.close_time,
        ):
            return trade

        if trade.status == TradeStatus.WAITING_ENTRY:
            return self._handle_waiting_entry(
                trade=trade,
                candle=candle,
            )

        return self._handle_active_trade(
            trade=trade,
            candle=candle,
        )

    def _handle_waiting_entry(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> ResearchTrade:
        """
        Activate trade when entry is reached.

        TP and SL are intentionally not checked in the entry candle.
        We cannot know the intrabar order from OHLC data alone.
        """

        if not self._entry_hit(
            trade=trade,
            candle=candle,
        ):
            trade.last_processed_candle_at = (
                candle.close_time
            )

            self.repository.save(trade)

            return trade

        trade.activate(
            opened_at=candle.close_time,
        )

        self.repository.save(trade)

        return trade

    def _handle_active_trade(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> ResearchTrade:
        """
        Update active trade using one completed candle.
        """

        trade.update_extremes(
            high=candle.high,
            low=candle.low,
        )

        trade.active_candles += 1
        trade.last_processed_candle_at = candle.close_time

        if self._stop_hit(
            trade=trade,
            candle=candle,
        ):
            trade.close(
                price=trade.stop_loss,
                reason="SL",
                closed_at=candle.close_time,
            )

        elif self._take_profit_hit(
            trade=trade,
            candle=candle,
        ):
            trade.close(
                price=trade.take_profit,
                reason="TP",
                closed_at=candle.close_time,
            )

        elif (
            trade.active_candles
            >= trade.max_active_candles
        ):
            trade.expire(
                price=candle.close,
                closed_at=candle.close_time,
            )

        self.repository.save(trade)

        return trade

    def _already_processed(
        self,
        trade: ResearchTrade,
        candle_time: datetime,
    ) -> bool:
        """
        Return True when candle was already stored for this trade.
        """

        last_time = trade.last_processed_candle_at

        if last_time is None:
            return False

        return self._naive_time(candle_time) <= self._naive_time(
            last_time
        )

    def _entry_hit(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> bool:
        """
        Return True when candle touched planned entry price.
        """

        return (
            candle.low
            <= trade.entry_price
            <= candle.high
        )

    def _stop_hit(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> bool:
        """
        Return True when candle touched Stop Loss.
        """

        if trade.is_long():
            return candle.low <= trade.stop_loss

        return candle.high >= trade.stop_loss

    def _take_profit_hit(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> bool:
        """
        Return True when candle touched Take Profit.
        """

        if trade.is_long():
            return candle.high >= trade.take_profit

        return candle.low <= trade.take_profit

    @staticmethod
    def _naive_time(
        value: datetime,
    ) -> datetime:
        """
        Compare exchange candle times without timezone-mismatch errors.
        """

        return value.replace(tzinfo=None)