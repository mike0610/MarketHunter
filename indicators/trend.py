"""
MarketHunter

indicators/trend.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot


class TrendFilter:
    """
    EMA trend filter.
    """

    def bullish(self, snapshot: MarketSnapshot) -> bool:
        """
        Bullish trend.
        """

        return (
            snapshot.ema20
            > snapshot.ema50
            > snapshot.ema200
        )

    def bearish(self, snapshot: MarketSnapshot) -> bool:
        """
        Bearish trend.
        """

        return (
            snapshot.ema20
            < snapshot.ema50
            < snapshot.ema200
        )