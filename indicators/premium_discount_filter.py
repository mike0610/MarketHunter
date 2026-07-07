"""
MarketHunter

indicators/premium_discount_filter.py
"""

from __future__ import annotations

from indicators.dealing_range_detector import (
    DealingRangeDetector,
)
from models.dealing_range import DealingRange
from models.market_snapshot import MarketSnapshot


class PremiumDiscountFilter:
    """
    Premium / Discount filter.
    """

    def __init__(self) -> None:

        self.detector = DealingRangeDetector()

    def dealing_range(
        self,
        snapshot: MarketSnapshot,
    ) -> DealingRange | None:

        return self.detector.detect(
            snapshot.candles,
        )

    def in_discount(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        dealing = self.dealing_range(snapshot)

        if dealing is None:
            return False

        return dealing.is_discount(
            snapshot.candles[-1].close,
        )

    def in_premium(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        dealing = self.dealing_range(snapshot)

        if dealing is None:
            return False

        return dealing.is_premium(
            snapshot.candles[-1].close,
        )

    def discount_percent(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        dealing = self.dealing_range(snapshot)

        if dealing is None:
            return 0.0

        return dealing.discount_percent(
            snapshot.candles[-1].close,
        )

    def premium_percent(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        dealing = self.dealing_range(snapshot)

        if dealing is None:
            return 0.0

        return dealing.premium_percent(
            snapshot.candles[-1].close,
        )