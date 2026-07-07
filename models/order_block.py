"""
MarketHunter

models/order_block.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OrderBlock:
    """
    Smart Money Order Block.
    """

    bullish: bool

    candle_index: int

    open: float

    high: float

    low: float

    close: float

    impulse_high: float

    impulse_low: float

    mitigated: bool = False

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