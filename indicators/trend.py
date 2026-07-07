"""
MarketHunter

indicators/trend.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class TrendFilter:
    """
    Trend filter using Market Structure Engine.
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

        return structure.bullish

    def bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        structure = self.engine.analyze(
            snapshot.candles,
        )

        return structure.bearish