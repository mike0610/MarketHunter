"""
MarketHunter

indicators/bos_filter.py
"""

from __future__ import annotations

from indicators.bos_detector import BOSDetector
from models.market_snapshot import MarketSnapshot


class BOSFilter:

    def __init__(self) -> None:
        self.detector = BOSDetector()

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

    def level(
        self,
        snapshot: MarketSnapshot,
    ) -> float | None:

        return self.detector.bullish_level(
            snapshot.candles,
        )