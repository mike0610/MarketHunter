"""
MarketHunter

models/mitigation_block.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MitigationBlock:
    """
    Represents a mitigated Order Block.
    """

    bullish: bool

    high: float

    low: float

    created_index: int

    mitigation_index: int

    touched: bool = False

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