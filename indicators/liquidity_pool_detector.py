"""
MarketHunter

indicators/liquidity_pool_detector.py
"""

from __future__ import annotations

from models.candle import Candle
from models.liquidity_pool import LiquidityPool
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class LiquidityPoolDetector:
    """
    Detect liquidity pools from market structure.
    """

    def __init__(self) -> None:

        self.structure = MarketStructureEngine()

    def bullish(
        self,
        candles: list[Candle],
    ) -> list[LiquidityPool]:

        market = self.structure.analyze(candles)

        if not market.bullish:
            return []

        pools: list[LiquidityPool] = []

        tolerance = (
            market.dealing_high
            - market.dealing_low
        ) * 0.002

        highs = []

        for i, candle in enumerate(candles):

            if abs(
                candle.high
                - market.last_high
            ) <= tolerance:

                highs.append(
                    (
                        i,
                        candle.high,
                    )
                )

        if len(highs) >= 2:

            pools.append(

                LiquidityPool(
                    bullish=False,
                    level=market.last_high,
                    first_index=highs[0][0],
                    last_index=highs[-1][0],
                    touches=len(highs),
                )

            )

        return pools

    def bearish(
        self,
        candles: list[Candle],
    ) -> list[LiquidityPool]:

        market = self.structure.analyze(candles)

        if not market.bearish:
            return []

        pools: list[LiquidityPool] = []

        tolerance = (
            market.dealing_high
            - market.dealing_low
        ) * 0.002

        lows = []

        for i, candle in enumerate(candles):

            if abs(
                candle.low
                - market.last_low
            ) <= tolerance:

                lows.append(
                    (
                        i,
                        candle.low,
                    )
                )

        if len(lows) >= 2:

            pools.append(

                LiquidityPool(
                    bullish=True,
                    level=market.last_low,
                    first_index=lows[0][0],
                    last_index=lows[-1][0],
                    touches=len(lows),
                )

            )

        return pools

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> LiquidityPool | None:

        pools = self.bullish(candles)

        return pools[-1] if pools else None

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> LiquidityPool | None:

        pools = self.bearish(candles)

        return pools[-1] if pools else None