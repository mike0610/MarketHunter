"""
MarketHunter

indicators/atr_filter.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot


class ATRFilter:
    """
    ATR impulse filter.
    """

    def __init__(
        self,
        multiplier: float = 1.0,
    ) -> None:

        self.multiplier = multiplier

    def bullish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        last = snapshot.candles[-1]

        return (
            last.body
            >= snapshot.atr14 * self.multiplier
        )

    def ratio(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        if snapshot.atr14 == 0:
            return 0.0

        last = snapshot.candles[-1]

        return last.body / snapshot.atr14