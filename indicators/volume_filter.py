"""
MarketHunter

indicators/volume_filter.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot


class VolumeFilter:
    """
    Volume confirmation filter.
    """

    def __init__(
        self,
        multiplier: float = 1.5,
    ) -> None:
        self.multiplier = multiplier

    def bullish(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        last = snapshot.candles[-1]

        return (
            last.volume
            >= snapshot.avg_volume20 * self.multiplier
        )

    def ratio(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        last = snapshot.candles[-1]

        if snapshot.avg_volume20 == 0:
            return 0.0

        return last.volume / snapshot.avg_volume20