"""
MarketHunter

engine/timeframe_engine.py
"""

from __future__ import annotations

from structure.market_structure_engine import (
    MarketStructureEngine,
)

from models.market_snapshot import MarketSnapshot
from models.timeframe_snapshot import (
    TimeframeSnapshot,
)


class TimeframeEngine:
    """
    Builds timeframe snapshots.
    """

    def __init__(self) -> None:

        self.structure = MarketStructureEngine()

    def build(
        self,
        snapshot: MarketSnapshot,
    ) -> TimeframeSnapshot:

        structure = self.structure.analyze(
            snapshot.candles,
        )

        return TimeframeSnapshot(
            timeframe=snapshot.timeframe,
            snapshot=snapshot,
            structure=structure,
        )