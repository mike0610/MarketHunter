"""
MarketHunter

indicators/breaker_detector.py
"""

from __future__ import annotations

from models.breaker_block import BreakerBlock
from models.candle import Candle
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class BreakerDetector:
    """
    Detect Breaker Blocks using Market Structure.
    """

    def __init__(self) -> None:

        self.structure = MarketStructureEngine()

    def bullish(
        self,
        candles: list[Candle],
    ) -> list[BreakerBlock]:

        market = self.structure.analyze(candles)

        if not market.bullish:
            return []

        blocks: list[BreakerBlock] = []

        for i in range(2, len(candles)):

            previous = candles[i - 1]
            current = candles[i]

            #
            # Previous candle failed,
            # current breaks structure.
            #

            if previous.close >= previous.open:
                continue

            if current.close <= market.last_high:
                continue

            blocks.append(

                BreakerBlock(
                    bullish=True,
                    high=previous.high,
                    low=previous.low,
                    created_index=i - 1,
                    break_index=i,
                    retest_index=None,
                )

            )

        return blocks

    def bearish(
        self,
        candles: list[Candle],
    ) -> list[BreakerBlock]:

        market = self.structure.analyze(candles)

        if not market.bearish:
            return []

        blocks: list[BreakerBlock] = []

        for i in range(2, len(candles)):

            previous = candles[i - 1]
            current = candles[i]

            if previous.close <= previous.open:
                continue

            if current.close >= market.last_low:
                continue

            blocks.append(

                BreakerBlock(
                    bullish=False,
                    high=previous.high,
                    low=previous.low,
                    created_index=i - 1,
                    break_index=i,
                    retest_index=None,
                )

            )

        return blocks

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> BreakerBlock | None:

        blocks = self.bullish(candles)

        return blocks[-1] if blocks else None

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> BreakerBlock | None:

        blocks = self.bearish(candles)

        return blocks[-1] if blocks else None