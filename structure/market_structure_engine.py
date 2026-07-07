"""
MarketHunter

structure/market_structure_engine.py
"""

from __future__ import annotations

from indicators.dealing_range_detector import (
    DealingRangeDetector,
)
from models.candle import Candle
from models.market_structure import MarketStructure
from structure.trend_engine import TrendEngine


class MarketStructureEngine:
    """
    Complete market structure engine.

    This engine becomes the single source of truth for:

    • Trend
    • HH
    • HL
    • LH
    • LL
    • BOS
    • CHoCH
    • Dealing Range
    """

    def __init__(self) -> None:

        self.trend = TrendEngine()
        self.dealing = DealingRangeDetector()

    def analyze(
        self,
        candles: list[Candle],
    ) -> MarketStructure:

        state = self.trend.analyze(candles)

        dealing = self.dealing.detect(candles)

        if dealing is None:

            highest = max(c.high for c in candles)
            lowest = min(c.low for c in candles)

        else:

            highest = dealing.high
            lowest = dealing.low

        last_close = candles[-1].close

        #
        # Break Of Structure
        #

        bos = False

        if state.last_high is not None:

            if last_close > state.last_high.price:

                bos = True

        if state.last_low is not None:

            if last_close < state.last_low.price:

                bos = True

        #
        # Change Of Character
        #

        choch = False

        if state.trend == "bullish":

            if (
                state.last_low is not None
                and last_close < state.last_low.price
            ):

                choch = True

        elif state.trend == "bearish":

            if (
                state.last_high is not None
                and last_close > state.last_high.price
            ):

                choch = True

        return MarketStructure(
            trend=state.trend,
            last_high=(
                state.last_high.price
                if state.last_high
                else 0.0
            ),
            last_low=(
                state.last_low.price
                if state.last_low
                else 0.0
            ),
            higher_high=state.higher_high,
            higher_low=state.higher_low,
            lower_high=state.lower_high,
            lower_low=state.lower_low,
            bos=bos,
            choch=choch,
            dealing_high=highest,
            dealing_low=lowest,
        )