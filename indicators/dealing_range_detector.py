"""
MarketHunter

indicators/dealing_range_detector.py
"""

from __future__ import annotations

from models.candle import Candle
from models.dealing_range import DealingRange


class DealingRangeDetector:
    """
    Detect ICT dealing range.
    """

    def detect(
        self,
        candles: list[Candle],
        lookback: int = 50,
    ) -> DealingRange | None:

        if len(candles) < lookback:
            return None

        history = candles[-lookback:]

        highest = max(
            c.high
            for c in history
        )

        lowest = min(
            c.low
            for c in history
        )

        return DealingRange(
            high=highest,
            low=lowest,
            start_index=len(candles) - lookback,
            end_index=len(candles) - 1,
        )