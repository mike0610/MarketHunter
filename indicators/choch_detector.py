"""
MarketHunter

indicators/choch_detector.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class CHoCHDetector:
    """
    Change Of Character detector.
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
            structure.choch
            and structure.bearish
        )

    def bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        structure = self.engine.analyze(
            snapshot.candles,
        )

        return (
            structure.choch
            and structure.bullish
        )

    def structure(
        self,
        snapshot: MarketSnapshot,
    ):

        return self.engine.analyze(
            snapshot.candles,
        )