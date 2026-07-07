"""
MarketHunter

indicators/pivot_detector.py
"""

from __future__ import annotations

from models.candle import Candle


class PivotDetector:
    """
    Detects swing highs and swing lows.
    """

    def swing_highs(
        self,
        candles: list[Candle],
        left: int = 3,
        right: int = 3,
    ) -> list[int]:

        pivots: list[int] = []

        for i in range(left, len(candles) - right):

            current = candles[i]

            if all(
                current.high > candles[j].high
                for j in range(i - left, i)
            ) and all(
                current.high >= candles[j].high
                for j in range(i + 1, i + right + 1)
            ):
                pivots.append(i)

        return pivots

    def swing_lows(
        self,
        candles: list[Candle],
        left: int = 3,
        right: int = 3,
    ) -> list[int]:

        pivots: list[int] = []

        for i in range(left, len(candles) - right):

            current = candles[i]

            if all(
                current.low < candles[j].low
                for j in range(i - left, i)
            ) and all(
                current.low <= candles[j].low
                for j in range(i + 1, i + right + 1)
            ):
                pivots.append(i)

        return pivots

    def last_swing_high(
        self,
        candles: list[Candle],
        left: int = 3,
        right: int = 3,
    ) -> Candle | None:

        pivots = self.swing_highs(
            candles,
            left,
            right,
        )

        if not pivots:
            return None

        return candles[pivots[-1]]

    def last_swing_low(
        self,
        candles: list[Candle],
        left: int = 3,
        right: int = 3,
    ) -> Candle | None:

        pivots = self.swing_lows(
            candles,
            left,
            right,
        )

        if not pivots:
            return None

        return candles[pivots[-1]]