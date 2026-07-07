"""
MarketHunter

indicators/breaker_filter.py
"""

from __future__ import annotations

from indicators.breaker_detector import BreakerDetector
from models.breaker_block import BreakerBlock
from models.market_snapshot import MarketSnapshot


class BreakerFilter:

    def __init__(self) -> None:

        self.detector = BreakerDetector()

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
    ) -> BreakerBlock | None:

        return self.detector.latest_bullish(
            snapshot.candles,
        )

    def latest_bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> BreakerBlock | None:

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