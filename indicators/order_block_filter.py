"""
MarketHunter

indicators/order_block_filter.py
"""

from __future__ import annotations

from indicators.order_block_detector import OrderBlockDetector
from models.market_snapshot import MarketSnapshot
from models.order_block import OrderBlock


class OrderBlockFilter:
    """
    Order Block filter.
    """

    def __init__(self) -> None:

        self.detector = OrderBlockDetector()

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
    ) -> OrderBlock | None:

        return self.detector.latest_bullish(
            snapshot.candles,
        )

    def latest_bearish(
        self,
        snapshot: MarketSnapshot,
    ) -> OrderBlock | None:

        return self.detector.latest_bearish(
            snapshot.candles,
        )

    def in_block(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        block = self.latest_bullish(snapshot)

        if block is None:
            return False

        return block.contains(
            snapshot.candles[-1].close,
        )