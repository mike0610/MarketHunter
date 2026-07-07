"""
MarketHunter

indicators/false_breakout.py
"""

from __future__ import annotations

from indicators.pivot_detector import PivotDetector
from models.candle import Candle


class FalseBreakoutDetector:
    """
    Detects false breakouts of swing levels.
    """

    def __init__(self) -> None:

        self.pivots = PivotDetector()

    def bearish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Price breaks previous swing high
        but closes back below it.
        """

        if len(candles) < 30:
            return False

        swing = self.pivots.last_swing_high(
            candles[:-1],
        )

        if swing is None:
            return False

        last = candles[-1]

        return (
            last.high > swing.high
            and last.close < swing.high
        )

    def bullish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Price breaks previous swing low
        but closes back above it.
        """

        if len(candles) < 30:
            return False

        swing = self.pivots.last_swing_low(
            candles[:-1],
        )

        if swing is None:
            return False

        last = candles[-1]

        return (
            last.low < swing.low
            and last.close > swing.low
        )

    def bearish_level(
        self,
        candles: list[Candle],
    ) -> float | None:

        swing = self.pivots.last_swing_high(
            candles[:-1],
        )

        return None if swing is None else swing.high

    def bullish_level(
        self,
        candles: list[Candle],
    ) -> float | None:

        swing = self.pivots.last_swing_low(
            candles[:-1],
        )

        return None if swing is None else swing.low