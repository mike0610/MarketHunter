"""
MarketHunter

Research Engine

Tracks virtual trades against real market candles.
"""

from __future__ import annotations

from models.candle import Candle
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.storage.repository import ResearchRepository


class TradeMonitor:
    """
    Updates one virtual trade using a newly completed candle.

    Conservative rule:
    if TP and SL are both inside the same candle,
    the trade closes at SL first.
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
        Update entry, TP, SL and excursion statistics.
        """

        if trade.status == TradeStatus.WAITING_ENTRY:

            if self._entry_hit(trade, candle):
                trade.activate(
                    opened_at=candle.open_time,
                )

        if trade.status != TradeStatus.ACTIVE:
            self.repository.save(trade)
            return trade

        trade.update_extremes(
            high=candle.high,
            low=candle.low,
        )

        # Conservative and reproducible backtest rule:
        # SL wins if TP and SL are hit inside the same candle.
        if self._stop_hit(trade, candle):

            trade.close(
                price=trade.stop_loss,
                reason="SL",
                closed_at=candle.close_time,
            )

        elif self._take_profit_hit(trade, candle):

            trade.close(
                price=trade.take_profit,
                reason="TP",
                closed_at=candle.close_time,
            )

        self.repository.save(trade)

        return trade

    def _entry_hit(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> bool:
        """
        Return True when candle touches entry level.
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
        Return True when stop loss is touched.
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
        Return True when take profit is touched.
        """

        if trade.is_long():
            return candle.high >= trade.take_profit

        return candle.low <= trade.take_profit