"""
MarketHunter

indicators/order_block_detector.py
"""

from __future__ import annotations

from models.candle import Candle
from models.order_block import OrderBlock
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class OrderBlockDetector:
    """
    Detect bullish and bearish Order Blocks using
    Market Structure Engine.
    """

    def __init__(self) -> None:

        self.structure = MarketStructureEngine()

    def bullish(
        self,
        candles: list[Candle],
    ) -> list[OrderBlock]:

        market = self.structure.analyze(candles)

        if not market.bullish:
            return []

        blocks: list[OrderBlock] = []

        for i in range(len(candles) - 2):

            candle = candles[i]

            #
            # Last bearish candle before impulse
            #

            if not candle.bearish:
                continue

            if candles[i + 1].close <= candle.high:
                continue

            blocks.append(

                OrderBlock(
                    bullish=True,
                    high=candle.high,
                    low=candle.low,
                    candle_index=i,
                )

            )

        return blocks

    def bearish(
        self,
        candles: list[Candle],
    ) -> list[OrderBlock]:

        market = self.structure.analyze(candles)

        if not market.bearish:
            return []

        blocks: list[OrderBlock] = []

        for i in range(len(candles) - 2):

            candle = candles[i]

            #
            # Last bullish candle before sell impulse
            #

            if not candle.bullish:
                continue

            if candles[i + 1].close >= candle.low:
                continue

            blocks.append(

                OrderBlock(
                    bullish=False,
                    high=candle.high,
                    low=candle.low,
                    candle_index=i,
                )

            )

        return blocks

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> OrderBlock | None:

        blocks = self.bullish(candles)

        return blocks[-1] if blocks else None

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> OrderBlock | None:

        blocks = self.bearish(candles)

        return blocks[-1] if blocks else None