"""
MarketHunter

Module:
CHoCH Detector

Responsibilities:
- Detect Change Of Character from completed candle data.
- Use MarketStructureEngine as the single source of structure state.
"""

from __future__ import annotations

from models.candle import Candle
from models.market_structure import MarketStructure
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class CHoCHDetector:
    """
    Detects Change Of Character from a candle sequence.

    Bullish CHoCH:
    prior structure was bearish and price breaks above the last swing high.

    Bearish CHoCH:
    prior structure was bullish and price breaks below the last swing low.
    """

    def __init__(self) -> None:
        self.engine = MarketStructureEngine()

    def bullish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Return True for a bullish Change Of Character.
        """

        structure = self.structure(candles)

        return (
            structure.choch
            and structure.bearish
        )

    def bearish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Return True for a bearish Change Of Character.
        """

        structure = self.structure(candles)

        return (
            structure.choch
            and structure.bullish
        )

    def bullish_level(
        self,
        candles: list[Candle],
    ) -> float | None:
        """
        Return the broken swing-high level for bullish CHoCH.
        """

        if not self.bullish(candles):
            return None

        structure = self.structure(candles)

        return structure.last_high

    def bearish_level(
        self,
        candles: list[Candle],
    ) -> float | None:
        """
        Return the broken swing-low level for bearish CHoCH.
        """

        if not self.bearish(candles):
            return None

        structure = self.structure(candles)

        return structure.last_low

    def structure(
        self,
        candles: list[Candle],
    ) -> MarketStructure:
        """
        Build market structure from raw candles.
        """

        return self.engine.analyze(candles)