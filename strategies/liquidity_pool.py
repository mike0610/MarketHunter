"""
MarketHunter

strategies/liquidity_pool.py
"""

from __future__ import annotations

from indicators.liquidity_pool_filter import (
    LiquidityPoolFilter,
)
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class LiquidityPoolStrategy(BaseStrategy):
    """
    Equal High / Equal Low strategy.
    """

    name = "LiquidityPool"

    def __init__(self) -> None:

        self.pool = LiquidityPoolFilter()
        self.trend = TrendFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        liquidity = self.pool.latest_bullish(
            snapshot,
        )

        if liquidity is None:
            return None

        score = 70

        trend_ok = self.trend.bullish(snapshot)
        volume_ok = self.volume.bullish(snapshot)

        if trend_ok:
            score += 15

        if volume_ok:
            score += 15

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction="LONG",
            score=score,
        )

        signal.add_reason(
            "Equal High Liquidity Pool"
        )

        signal.add_reason(
            f"Liquidity {liquidity.level:.4f}"
        )

        signal.add_reason(
            f"Distance {self.pool.distance_percent(snapshot):.2f}%"
        )

        if trend_ok:

            signal.add_reason(
                "Bullish EMA trend"
            )

        if volume_ok:

            signal.add_reason(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        return signal