"""
MarketHunter

Module:
Liquidity Pool Detector

Responsibilities:
- Detect equal highs as buy-side liquidity.
- Detect equal lows as sell-side liquidity.
- Use Market Structure as a directional filter.
"""

from __future__ import annotations

from models.candle import Candle
from models.liquidity_pool import LiquidityPool
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class LiquidityPoolDetector:
    """
    Detects liquidity pools from repeated equal highs and equal lows.
    """

    MIN_TOUCHES = 2
    TOLERANCE_RATIO = 0.002

    def __init__(self) -> None:
        self.structure = MarketStructureEngine()

    def bullish(
        self,
        candles: list[Candle],
    ) -> list[LiquidityPool]:
        """
        Detect buy-side liquidity above equal highs.

        The pool itself is marked bullish=False because equal highs
        represent buy-side liquidity above price.
        """

        if len(candles) < self.MIN_TOUCHES:
            return []

        market = self.structure.analyze(candles)

        if not market.bullish:
            return []

        if (
            market.last_high is None
            or market.dealing_high is None
            or market.dealing_low is None
        ):
            return []

        dealing_range = (
            market.dealing_high
            - market.dealing_low
        )

        if dealing_range <= 0:
            return []

        tolerance = (
            dealing_range
            * self.TOLERANCE_RATIO
        )

        touches = [
            (index, candle.high)
            for index, candle in enumerate(candles)
            if abs(candle.high - market.last_high)
            <= tolerance
        ]

        if len(touches) < self.MIN_TOUCHES:
            return []

        return [
            LiquidityPool(
                bullish=False,
                level=market.last_high,
                first_index=touches[0][0],
                second_index=touches[-1][0],
                touches=len(touches),
            )
        ]

    def bearish(
        self,
        candles: list[Candle],
    ) -> list[LiquidityPool]:
        """
        Detect sell-side liquidity below equal lows.

        The pool itself is marked bullish=True because equal lows
        represent sell-side liquidity below price.
        """

        if len(candles) < self.MIN_TOUCHES:
            return []

        market = self.structure.analyze(candles)

        if not market.bearish:
            return []

        if (
            market.last_low is None
            or market.dealing_high is None
            or market.dealing_low is None
        ):
            return []

        dealing_range = (
            market.dealing_high
            - market.dealing_low
        )

        if dealing_range <= 0:
            return []

        tolerance = (
            dealing_range
            * self.TOLERANCE_RATIO
        )

        touches = [
            (index, candle.low)
            for index, candle in enumerate(candles)
            if abs(candle.low - market.last_low)
            <= tolerance
        ]

        if len(touches) < self.MIN_TOUCHES:
            return []

        return [
            LiquidityPool(
                bullish=True,
                level=market.last_low,
                first_index=touches[0][0],
                second_index=touches[-1][0],
                touches=len(touches),
            )
        ]

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> LiquidityPool | None:
        """
        Return the newest sell-side liquidity pool.
        """

        pools = self.bullish(candles)

        return pools[-1] if pools else None

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> LiquidityPool | None:
        """
        Return the newest buy-side liquidity pool.
        """

        pools = self.bearish(candles)

        return pools[-1] if pools else None