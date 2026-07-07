"""
MarketHunter

models/breaker_block.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BreakerBlock:
    """
    Smart Money Breaker Block.
    """

    bullish: bool

    high: float

    low: float

    created_index: int

    break_index: int

    retest_index: int | None = None

    @property
    def midpoint(self) -> float:

        return (self.high + self.low) / 2

    @property
    def range(self) -> float:

        return self.high - self.low

    def contains(
        self,
        price: float,
    ) -> bool:

        return self.low <= price <= self.high