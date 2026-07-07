"""
MarketHunter

Module:
BOS Detector

Responsibilities:
- Detect bullish and bearish Break Of Structure.
- Use MarketStructureEngine as the single source of structure state.
"""

from __future__ import annotations

from models.candle import Candle
from models.market_structure import MarketStructure
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class BOSDetector:
    """
    Detects Break Of Structure from a candle sequence.
    """

    def __init__(self) -> None:
        self.engine = MarketStructureEngine()

    def bullish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Return True when bullish market structure breaks upward.
        """

        structure = self.structure(candles)

        return (
            structure.bos
            and structure.bullish
        )

    def bearish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Return True when bearish market structure breaks downward.
        """

        structure = self.structure(candles)

        return (
            structure.bos
            and structure.bearish
        )

    def bullish_level(
        self,
        candles: list[Candle],
    ) -> float | None:
        """
        Return broken swing-high level for bullish BOS.
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
        Return broken swing-low level for bearish BOS.
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