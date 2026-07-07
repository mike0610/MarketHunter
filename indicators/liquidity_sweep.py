"""
MarketHunter

indicators/liquidity_sweep.py
"""

from __future__ import annotations

from models.candle import Candle
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class LiquiditySweepDetector:
    """
    Detects liquidity sweeps using Market Structure Engine.
    """

    def __init__(self) -> None:

        self.structure = MarketStructureEngine()

    def bullish(
        self,
        candles: list[Candle],
    ) -> bool:

        market = self.structure.analyze(candles)

        if not market.bullish:
            return False

        if len(candles) < 3:
            return False

        last = candles[-1]

        #
        # Sweep previous swing low
        #

        return (
            last.low < market.last_low
            and last.close > market.last_low
        )

    def bearish(
        self,
        candles: list[Candle],
    ) -> bool:

        market = self.structure.analyze(candles)

        if not market.bearish:
            return False

        if len(candles) < 3:
            return False

        last = candles[-1]

        #
        # Sweep previous swing high
        #

        return (
            last.high > market.last_high
            and last.close < market.last_high
        )

    def sweep_level(
        self,
        candles: list[Candle],
    ) -> float | None:

        market = self.structure.analyze(candles)

        last = candles[-1]

        if (
            last.low < market.last_low
            and last.close > market.last_low
        ):
            return market.last_low

        if (
            last.high > market.last_high
            and last.close < market.last_high
        ):
            return market.last_high

        return None