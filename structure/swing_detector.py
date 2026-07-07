"""
MarketHunter

structure/swing_detector.py
"""

from __future__ import annotations

from dataclasses import dataclass

from models.candle import Candle


@dataclass(slots=True)
class SwingPoint:
    """
    Swing High / Swing Low.
    """

    index: int

    price: float

    kind: str  # "high" | "low"


class SwingDetector:
    """
    Detects market swing highs and swing lows.

    Uses symmetric lookback/lookforward window.
    """

    def __init__(
        self,
        left: int = 3,
        right: int = 3,
    ) -> None:

        self.left = left
        self.right = right

    def highs(
        self,
        candles: list[Candle],
    ) -> list[SwingPoint]:

        swings: list[SwingPoint] = []

        if len(candles) < self.left + self.right + 1:
            return swings

        for i in range(
            self.left,
            len(candles) - self.right,
        ):

            current = candles[i].high

            is_high = True

            #
            # Left
            #

            for j in range(
                i - self.left,
                i,
            ):

                if candles[j].high >= current:

                    is_high = False

                    break

            if not is_high:
                continue

            #
            # Right
            #

            for j in range(
                i + 1,
                i + self.right + 1,
            ):

                if candles[j].high > current:

                    is_high = False

                    break

            if is_high:

                swings.append(

                    SwingPoint(
                        index=i,
                        price=current,
                        kind="high",
                    )

                )

        return swings

    def lows(
        self,
        candles: list[Candle],
    ) -> list[SwingPoint]:

        swings: list[SwingPoint] = []

        if len(candles) < self.left + self.right + 1:
            return swings

        for i in range(
            self.left,
            len(candles) - self.right,
        ):

            current = candles[i].low

            is_low = True

            #
            # Left
            #

            for j in range(
                i - self.left,
                i,
            ):

                if candles[j].low <= current:

                    is_low = False

                    break

            if not is_low:
                continue

            #
            # Right
            #

            for j in range(
                i + 1,
                i + self.right + 1,
            ):

                if candles[j].low < current:

                    is_low = False

                    break

            if is_low:

                swings.append(

                    SwingPoint(
                        index=i,
                        price=current,
                        kind="low",
                    )

                )

        return swings

    def last_high(
        self,
        candles: list[Candle],
    ) -> SwingPoint | None:

        highs = self.highs(candles)

        if not highs:
            return None

        return highs[-1]

    def last_low(
        self,
        candles: list[Candle],
    ) -> SwingPoint | None:

        lows = self.lows(candles)

        if not lows:
            return None

        return lows[-1]