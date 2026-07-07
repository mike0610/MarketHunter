"""
MarketHunter

indicators/bos_detector.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class BOSDetector:
    """
    Break Of Structure detector.
    """

    def __init__(self) -> None:

        self.engine = MarketStructureEngine()

    def bullish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        structure = self.engine.analyze(
            snapshot.candles,
        )

        return (
            structure.bos
            and structure.bullish
        )

    def bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        structure = self.engine.analyze(
            snapshot.candles,
        )

        return (
            structure.bos
            and structure.bearish
        )

    def structure(
        self,
        snapshot: MarketSnapshot,
    ):

        return self.engine.analyze(
            snapshot.candles,
        )