"""
MarketHunter

strategies/premium_discount.py
"""

from __future__ import annotations

from indicators.premium_discount_filter import (
    PremiumDiscountFilter,
)
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class PremiumDiscountStrategy(BaseStrategy):
    """
    ICT Premium / Discount strategy.
    """

    name = "PremiumDiscount"

    def __init__(self) -> None:

        self.zone = PremiumDiscountFilter()
        self.trend = TrendFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        if not self.zone.in_discount(snapshot):
            return None

        score = 70

        trend_ok = self.trend.bullish(snapshot)
        volume_ok = self.volume.bullish(snapshot)

        if trend_ok:
            score += 15

        if volume_ok:
            score += 15

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction="LONG",
            score=score,
        )

        signal.add_reason(
            "Price in Discount Zone"
        )

        signal.add_reason(
            f"Discount {self.zone.discount_percent(snapshot):.1f}%"
        )

        if trend_ok:

            signal.add_reason(
                "Bullish EMA trend"
            )

        if volume_ok:

            signal.add_reason(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        return signal