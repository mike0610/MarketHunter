"""
MarketHunter

Research Engine

Module:
Trade Monitor

Version:
0.2
"""

from __future__ import annotations

from models.candle import Candle
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.storage.repository import ResearchRepository


class TradeMonitor:
    """
    Monitors virtual trades against real candles.
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

        if trade.status == TradeStatus.WAITING_ENTRY:

            if self._entry_hit(trade, candle):
                trade.activate()

        if trade.status != TradeStatus.ACTIVE:
            self.repository.save(trade)
            return trade

        self._update_extremes(trade, candle)

        if self._stop_hit(trade, candle):
            trade.close(
                trade.stop_loss,
                "SL",
            )

        elif self._take_profit_hit(trade, candle):
            trade.close(
                trade.take_profit,
                "TP",
            )

        self.repository.save(trade)

        return trade

    def _entry_hit(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> bool:

        return (
            candle.low <= trade.entry_price <= candle.high
        )

    def _stop_hit(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> bool:

        if trade.is_long():
            return candle.low <= trade.stop_loss

        return candle.high >= trade.stop_loss

    def _take_profit_hit(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> bool:

        if trade.is_long():
            return candle.high >= trade.take_profit

        return candle.low <= trade.take_profit

    def _update_extremes(
        self,
        trade: ResearchTrade,
        candle: Candle,
    ) -> None:

        if trade.is_long():

            max_profit = (
                (candle.high - trade.entry_price)
                / trade.entry_price
            ) * 100

            max_drawdown = (
                (candle.low - trade.entry_price)
                / trade.entry_price
            ) * 100

        else:

            max_profit = (
                (trade.entry_price - candle.low)
                / trade.entry_price
            ) * 100

            max_drawdown = (
                (trade.entry_price - candle.high)
                / trade.entry_price
            ) * 100

        trade.max_profit_percent = max(
            trade.max_profit_percent,
            max_profit,
        )

        trade.max_drawdown_percent = min(
            trade.max_drawdown_percent,
            max_drawdown,
        )