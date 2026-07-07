"""
MarketHunter

models/fvg.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FVG:
    """
    Fair Value Gap.
    """

    bullish: bool

    start_index: int

    end_index: int

    upper: float

    lower: float

    size: float

    filled: bool = False

    @property
    def midpoint(self) -> float:

        return (self.upper + self.lower) / 2

    @property
    def percent(self) -> float:

        if self.lower == 0:
            return 0.0

        return self.size / self.lower * 100