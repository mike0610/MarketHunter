"""
MarketHunter

strategies/breaker.py
"""

from __future__ import annotations

from indicators.breaker_filter import BreakerFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class BreakerStrategy(BaseStrategy):

    name = "Breaker"

    def __init__(self) -> None:

        self.breaker = BreakerFilter()
        self.trend = TrendFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        block = self.breaker.latest_bullish(
            snapshot,
        )

        if block is None:
            return None

        score = 80

        trend = self.trend.bullish(snapshot)
        volume = self.volume.bullish(snapshot)
        inside = self.breaker.inside(snapshot)

        if trend:
            score += 10

        if volume:
            score += 10

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction="LONG",
            score=score,
        )

        signal.add_reason(
            "Bullish Breaker Block"
        )

        signal.add_reason(
            f"Zone {block.low:.4f}-{block.high:.4f}"
        )

        if block.retest_index is not None:

            signal.add_reason(
                "Breaker retest confirmed"
            )

        if inside:

            signal.add_reason(
                "Price inside breaker"
            )

        if trend:

            signal.add_reason(
                "Bullish EMA trend"
            )

        if volume:

            signal.add_reason(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        return signal