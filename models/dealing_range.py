"""
MarketHunter

models/dealing_range.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DealingRange:
    """
    ICT Dealing Range.
    """

    high: float

    low: float

    start_index: int

    end_index: int

    @property
    def midpoint(self) -> float:

        return (self.high + self.low) / 2

    @property
    def premium(self) -> float:

        return self.midpoint

    @property
    def discount(self) -> float:

        return self.midpoint

    def is_premium(
        self,
        price: float,
    ) -> bool:

        return price >= self.midpoint

    def is_discount(
        self,
        price: float,
    ) -> bool:

        return price < self.midpoint

    def premium_percent(
        self,
        price: float,
    ) -> float:

        if price <= self.midpoint:
            return 0.0

        return (
            (price - self.midpoint)
            / (self.high - self.midpoint)
        ) * 100

    def discount_percent(
        self,
        price: float,
    ) -> float:

        if price >= self.midpoint:
            return 0.0

        return (
            (self.midpoint - price)
            / (self.midpoint - self.low)
        ) * 100