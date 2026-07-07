"""
MarketHunter

indicators/liquidity_filter.py
"""

from __future__ import annotations

from indicators.liquidity_sweep import LiquiditySweepDetector
from models.market_snapshot import MarketSnapshot


class LiquidityFilter:

    def __init__(self) -> None:
        self.detector = LiquiditySweepDetector()

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