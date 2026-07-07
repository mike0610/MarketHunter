"""
MarketHunter

indicators/false_breakout_filter.py
"""

from __future__ import annotations

from indicators.false_breakout import FalseBreakoutDetector
from models.market_snapshot import MarketSnapshot


class FalseBreakoutFilter:

    def __init__(self) -> None:

        self.detector = FalseBreakoutDetector()

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