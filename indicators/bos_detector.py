"""
MarketHunter

indicators/bos_detector.py
"""

from __future__ import annotations

from indicators.pivot_detector import PivotDetector
from models.candle import Candle


class BOSDetector:
    """
    Break Of Structure detector.
    """

    def __init__(self) -> None:
        self.pivots = PivotDetector()

    def bullish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Bullish BOS.
        """

        if len(candles) < 20:
            return False

        swing = self.pivots.last_swing_high(
            candles[:-1],
        )

        if swing is None:
            return False

        return candles[-1].close > swing.high

    def bearish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Bearish BOS.
        """

        if len(candles) < 20:
            return False

        swing = self.pivots.last_swing_low(
            candles[:-1],
        )

        if swing is None:
            return False

        return candles[-1].close < swing.low

    def bullish_level(
        self,
        candles: list[Candle],
    ) -> float | None:

        swing = self.pivots.last_swing_high(
            candles[:-1],
        )

        if swing is None:
            return None

        return swing.high

    def bearish_level(
        self,
        candles: list[Candle],
    ) -> float | None:

        swing = self.pivots.last_swing_low(
            candles[:-1],
        )

        if swing is None:
            return None

        return swing.low