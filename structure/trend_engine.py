"""
MarketHunter

structure/trend_engine.py
"""

from __future__ import annotations

from dataclasses import dataclass

from models.candle import Candle
from structure.swing_detector import (
    SwingDetector,
    SwingPoint,
)


@dataclass(slots=True)
class TrendState:
    """
    Current market trend state.
    """

    trend: str

    higher_high: bool

    higher_low: bool

    lower_high: bool

    lower_low: bool

    last_high: SwingPoint | None

    last_low: SwingPoint | None


class TrendEngine:
    """
    Detects market trend using swing structure.
    """

    def __init__(self) -> None:

        self.swings = SwingDetector()

    def analyze(
        self,
        candles: list[Candle],
    ) -> TrendState:

        highs = self.swings.highs(candles)
        lows = self.swings.lows(candles)

        if len(highs) < 2 or len(lows) < 2:

            return TrendState(
                trend="sideways",
                higher_high=False,
                higher_low=False,
                lower_high=False,
                lower_low=False,
                last_high=highs[-1] if highs else None,
                last_low=lows[-1] if lows else None,
            )

        last_high = highs[-1]
        prev_high = highs[-2]

        last_low = lows[-1]
        prev_low = lows[-2]

        higher_high = (
            last_high.price >
            prev_high.price
        )

        lower_high = (
            last_high.price <
            prev_high.price
        )

        higher_low = (
            last_low.price >
            prev_low.price
        )

        lower_low = (
            last_low.price <
            prev_low.price
        )

        if higher_high and higher_low:

            trend = "bullish"

        elif lower_high and lower_low:

            trend = "bearish"

        else:

            trend = "sideways"

        return TrendState(
            trend=trend,
            higher_high=higher_high,
            higher_low=higher_low,
            lower_high=lower_high,
            lower_low=lower_low,
            last_high=last_high,
            last_low=last_low,
        )