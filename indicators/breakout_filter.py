"""
MarketHunter

indicators/breakout_filter.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot


class BreakoutFilter:
    """
    Breakout confirmation filter.
    """

    def bullish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        last = snapshot.candles[-1]

        return last.close > snapshot.highest20

    def breakout_percent(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        last = snapshot.candles[-1]

        if snapshot.highest20 == 0:
            return 0.0

        return (
            (last.close - snapshot.highest20)
            / snapshot.highest20
        ) * 100