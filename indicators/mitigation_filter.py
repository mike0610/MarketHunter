"""
MarketHunter

indicators/mitigation_filter.py
"""

from __future__ import annotations

from indicators.mitigation_detector import MitigationDetector
from models.market_snapshot import MarketSnapshot
from models.mitigation_block import MitigationBlock


class MitigationFilter:
    """
    Mitigation Block filter.
    """

    def __init__(self) -> None:

        self.detector = MitigationDetector()

    def bullish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        return self.latest_bullish(snapshot) is not None

    def bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        return self.latest_bearish(snapshot) is not None

    def latest_bullish(
        self,
        snapshot: MarketSnapshot,
    ) -> MitigationBlock | None:

        return self.detector.latest_bullish(
            snapshot.candles,
        )

    def latest_bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> MitigationBlock | None:

        return self.detector.latest_bearish(
            snapshot.candles,
        )

    def inside(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        block = self.latest_bullish(snapshot)

        if block is None:
            return False

        return block.contains(
            snapshot.candles[-1].close,
        )

    def distance_percent(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        block = self.latest_bullish(snapshot)

        if block is None:
            return 0.0

        close = snapshot.candles[-1].close

        return abs(
            close - block.midpoint
        ) / close * 100