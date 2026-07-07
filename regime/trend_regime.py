"""
MarketHunter

regime/trend_regime.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class TrendRegime:

    def __init__(self):

        self.structure = MarketStructureEngine()

    def bullish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        return self.structure.analyze(
            snapshot.candles,
        ).bullish

    def bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        return self.structure.analyze(
            snapshot.candles,
        ).bearish