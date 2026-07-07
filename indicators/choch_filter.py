"""
MarketHunter

indicators/choch_filter.py
"""

from __future__ import annotations

from indicators.choch_detector import CHoCHDetector
from models.market_snapshot import MarketSnapshot


class CHoCHFilter:
    """
    Change Of Character filter.
    """

    def __init__(self) -> None:

        self.detector = CHoCHDetector()

    def bullish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        return self.detector.bullish(
            snapshot.candles,
        )

    def bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        return self.detector.bearish(
            snapshot.candles,
        )

    def bullish_level(
        self,
        snapshot: MarketSnapshot,
    ) -> float | None:

        return self.detector.bullish_level(
            snapshot.candles,
        )

    def bearish_level(
        self,
        snapshot: MarketSnapshot,
    ) -> float | None:

        return self.detector.bearish_level(
            snapshot.candles,
        )