"""
MarketHunter

backtesting/trade_simulator.py
"""

from __future__ import annotations

from models.position import Position


class TradeSimulator:

    def long(
        self,
        position: Position,
        candles,
    ) -> float:

        for candle in candles:

            if candle.low <= position.stop_loss:

                return (
                    position.stop_loss
                    - position.entry
                ) * position.quantity

            if candle.high >= position.take_profit:

                return (
                    position.take_profit
                    - position.entry
                ) * position.quantity

        return (
            candles[-1].close
            - position.entry
        ) * position.quantity

    def short(
        self,
        position: Position,
        candles,
    ) -> float:

        for candle in candles:

            if candle.high >= position.stop_loss:

                return (
                    position.entry
                    - position.stop_loss
                ) * position.quantity

            if candle.low <= position.take_profit:

                return (
                    position.entry
                    - position.take_profit
                ) * position.quantity

        return (
            position.entry
            - candles[-1].close
        ) * position.quantity