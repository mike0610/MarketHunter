"""
MarketHunter

strategies/order_block.py
"""

from __future__ import annotations

from indicators.order_block_filter import OrderBlockFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class OrderBlockStrategy(BaseStrategy):
    """
    Bullish Order Block strategy.
    """

    name = "OrderBlock"

    def __init__(self) -> None:

        self.order_block = OrderBlockFilter()
        self.trend = TrendFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        block = self.order_block.latest_bullish(
            snapshot,
        )

        if block is None:
            return None

        score = 75

        trend_ok = self.trend.bullish(snapshot)
        volume_ok = self.volume.bullish(snapshot)
        inside_block = self.order_block.in_block(snapshot)

        if trend_ok:
            score += 10

        if volume_ok:
            score += 10

        if inside_block:
            score += 5

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction="LONG",
            score=score,
        )

        signal.add_reason(
            "Bullish Order Block"
        )

        signal.add_reason(
            f"Zone {block.low:.4f} - {block.high:.4f}"
        )

        if inside_block:

            signal.add_reason(
                "Price inside Order Block"
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