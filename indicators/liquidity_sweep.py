"""
MarketHunter

indicators/liquidity_sweep.py
"""

from __future__ import annotations

from indicators.pivot_detector import PivotDetector
from models.candle import Candle


class LiquiditySweepDetector:
    """
    Detects liquidity sweeps.
    """

    def __init__(self) -> None:
        self.pivots = PivotDetector()

    def bullish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Bullish liquidity sweep.
        """

        if len(candles) < 20:
            return False

        last = candles[-1]

        swing = self.pivots.last_swing_low(
            candles[:-1],
        )

        if swing is None:
            return False

        return (
            last.low < swing.low
            and last.close > swing.low
        )

    def bearish(
        self,
        candles: list[Candle],
    ) -> bool:
        """
        Bearish liquidity sweep.
        """

        if len(candles) < 20:
            return False

        last = candles[-1]

        swing = self.pivots.last_swing_high(
            candles[:-1],
        )

        if swing is None:
            return False

        return (
            last.high > swing.high
            and last.close < swing.high
        )

    def bullish_level(
        self,
        candles: list[Candle],
    ) -> float | None:

        swing = self.pivots.last_swing_low(
            candles[:-1],
        )

        if swing is None:
            return None

        return swing.low

    def bearish_level(
        self,
        candles: list[Candle],
    ) -> float | None:

        swing = self.pivots.last_swing_high(
            candles[:-1],
        )

        if swing is None:
            return None

        return swing.high