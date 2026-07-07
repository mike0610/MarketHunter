"""
MarketHunter

indicators/fvg_filter.py
"""

from __future__ import annotations

from indicators.fvg_detector import FVGDetector
from models.fvg import FVG
from models.market_snapshot import MarketSnapshot


class FVGFilter:
    """
    Fair Value Gap filter.
    """

    def __init__(self) -> None:

        self.detector = FVGDetector()

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
    ) -> FVG | None:

        return self.detector.latest_bullish(
            snapshot.candles,
        )

    def latest_bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> FVG | None:

        return self.detector.latest_bearish(
            snapshot.candles,
        )

    def size_percent(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        gap = self.latest_bullish(snapshot)

        if gap is None:
            return 0.0

        return gap.percent