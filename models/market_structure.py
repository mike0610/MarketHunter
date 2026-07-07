"""
MarketHunter

models/market_structure.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MarketStructure:
    """
    Complete market structure.
    """

    trend: str

    last_high: float

    last_low: float

    higher_high: bool

    higher_low: bool

    lower_high: bool

    lower_low: bool

    bos: bool

    choch: bool

    dealing_high: float

    dealing_low: float

    @property
    def bullish(self) -> bool:

        return self.trend == "bullish"

    @property
    def bearish(self) -> bool:

        return self.trend == "bearish"