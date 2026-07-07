"""
MarketHunter

models/market_regime.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MarketRegime:
    """
    Current market regime.
    """

    trend: bool

    range: bool

    compression: bool

    expansion: bool

    volatility: float

    atr_ratio: float

    name: str

    score: int

    @property
    def tradable(self) -> bool:

        return (
            self.trend
            or self.expansion
        )

    @property
    def avoid(self) -> bool:

        return (
            self.range
            or self.compression
        )