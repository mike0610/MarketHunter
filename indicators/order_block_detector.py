"""
MarketHunter

Module:
Order Block Detector

Responsibilities:
- Detect bullish and bearish order blocks.
- Preserve source candle and impulse data.
- Use Market Structure as a directional filter.
"""

from __future__ import annotations

from models.candle import Candle
from models.order_block import OrderBlock
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class OrderBlockDetector:
    """
    Detects bullish and bearish order blocks.

    A bullish order block is the last bearish candle before
    an upward displacement. A bearish order block is the last
    bullish candle before a downward displacement.
    """

    MIN_CANDLES = 3

    def __init__(self) -> None:
        self.structure = MarketStructureEngine()

    def bullish(
        self,
        candles: list[Candle],
    ) -> list[OrderBlock]:
        """
        Return bullish order blocks for a bullish market structure.
        """

        if len(candles) < self.MIN_CANDLES:
            return []

        market = self.structure.analyze(candles)

        if not market.bullish:
            return []

        blocks: list[OrderBlock] = []

        for index in range(len(candles) - 2):
            source = candles[index]
            impulse_first = candles[index + 1]
            impulse_second = candles[index + 2]

            if not source.bearish:
                continue

            if impulse_first.close <= source.high:
                continue

            blocks.append(
                OrderBlock(
                    bullish=True,
                    candle_index=index,
                    open=source.open,
                    high=source.high,
                    low=source.low,
                    close=source.close,
                    impulse_high=max(
                        impulse_first.high,
                        impulse_second.high,
                    ),
                    impulse_low=min(
                        source.low,
                        impulse_first.low,
                        impulse_second.low,
                    ),
                )
            )

        return blocks

    def bearish(
        self,
        candles: list[Candle],
    ) -> list[OrderBlock]:
        """
        Return bearish order blocks for a bearish market structure.
        """

        if len(candles) < self.MIN_CANDLES:
            return []

        market = self.structure.analyze(candles)

        if not market.bearish:
            return []

        blocks: list[OrderBlock] = []

        for index in range(len(candles) - 2):
            source = candles[index]
            impulse_first = candles[index + 1]
            impulse_second = candles[index + 2]

            if not source.bullish:
                continue

            if impulse_first.close >= source.low:
                continue

            blocks.append(
                OrderBlock(
                    bullish=False,
                    candle_index=index,
                    open=source.open,
                    high=source.high,
                    low=source.low,
                    close=source.close,
                    impulse_high=max(
                        source.high,
                        impulse_first.high,
                        impulse_second.high,
                    ),
                    impulse_low=min(
                        impulse_first.low,
                        impulse_second.low,
                    ),
                )
            )

        return blocks

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> OrderBlock | None:
        """
        Return the newest bullish order block.
        """

        blocks = self.bullish(candles)

        return blocks[-1] if blocks else None

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> OrderBlock | None:
        """
        Return the newest bearish order block.
        """

        blocks = self.bearish(candles)

        return blocks[-1] if blocks else None