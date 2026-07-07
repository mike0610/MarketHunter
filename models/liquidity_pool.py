"""
MarketHunter

models/liquidity_pool.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LiquidityPool:
    """
    Equal High / Equal Low liquidity pool.
    """

    bullish: bool

    level: float

    first_index: int

    second_index: int

    touches: int

    swept: bool = False

    @property
    def type(self) -> str:

        return "SELL_SIDE" if self.bullish else "BUY_SIDE"