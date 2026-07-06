"""
MarketHunter

indicators/support_resistance.py
"""

from __future__ import annotations

from models.candle import Candle


class SupportResistance:
    """
    Finds important support and resistance levels.
    """

    def resistance(
        self,
        candles: list[Candle],
        lookback: int = 20,
    ) -> float:

        history = candles[-lookback - 1:-1]

        return max(c.high for c in history)

    def support(
        self,
        candles: list[Candle],
        lookback: int = 20,
    ) -> float:

        history = candles[-lookback - 1:-1]

        return min(c.low for c in history)

    def breakout(
        self,
        candles: list[Candle],
        lookback: int = 20,
    ) -> bool:

        if len(candles) < lookback + 1:
            return False

        last = candles[-1]

        return (
            last.close >
            self.resistance(candles, lookback)
        )

    def breakdown(
        self,
        candles: list[Candle],
        lookback: int = 20,
    ) -> bool:

        if len(candles) < lookback + 1:
            return False

        last = candles[-1]

        return (
            last.close <
            self.support(candles, lookback)
        )