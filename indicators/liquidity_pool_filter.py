"""
MarketHunter

indicators/liquidity_pool_filter.py
"""

from __future__ import annotations

from indicators.liquidity_pool_detector import (
    LiquidityPoolDetector,
)
from models.liquidity_pool import LiquidityPool
from models.market_snapshot import MarketSnapshot


class LiquidityPoolFilter:
    """
    Liquidity Pool filter.
    """

    def __init__(self) -> None:

        self.detector = LiquidityPoolDetector()

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
    ) -> LiquidityPool | None:

        return self.detector.latest_bullish(
            snapshot.candles,
        )

    def latest_bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> LiquidityPool | None:

        return self.detector.latest_bearish(
            snapshot.candles,
        )

    def distance_percent(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        pool = self.latest_bullish(snapshot)

        if pool is None:
            return 0.0

        close = snapshot.candles[-1].close

        return abs(close - pool.level) / close * 100