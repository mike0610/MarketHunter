"""
MarketHunter

indicators/fvg_detector.py
"""

from __future__ import annotations

from models.candle import Candle
from models.fvg import FVG


class FVGDetector:
    """
    Detect Fair Value Gaps.
    """

    def bullish(
        self,
        candles: list[Candle],
    ) -> list[FVG]:

        gaps: list[FVG] = []

        if len(candles) < 5:
            return gaps

        for i in range(2, len(candles)):

            left = candles[i - 2]
            middle = candles[i - 1]
            right = candles[i]

            #
            # Bullish imbalance
            #

            if left.high >= right.low:
                continue

            upper = right.low
            lower = left.high

            gaps.append(

                FVG(
                    bullish=True,
                    start_index=i - 2,
                    end_index=i,
                    upper=upper,
                    lower=lower,
                    size=upper - lower,
                )

            )

        return gaps

    def bearish(
        self,
        candles: list[Candle],
    ) -> list[FVG]:

        gaps: list[FVG] = []

        if len(candles) < 5:
            return gaps

        for i in range(2, len(candles)):

            left = candles[i - 2]
            middle = candles[i - 1]
            right = candles[i]

            #
            # Bearish imbalance
            #

            if left.low <= right.high:
                continue

            upper = left.low
            lower = right.high

            gaps.append(

                FVG(
                    bullish=False,
                    start_index=i - 2,
                    end_index=i,
                    upper=upper,
                    lower=lower,
                    size=upper - lower,
                )

            )

        return gaps

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> FVG | None:

        gaps = self.bullish(candles)

        if not gaps:
            return None

        return gaps[-1]

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> FVG | None:

        gaps = self.bearish(candles)

        if not gaps:
            return None

        return gaps[-1]