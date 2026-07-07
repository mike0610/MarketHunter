"""
MarketHunter

strategies/mitigation.py
"""

from __future__ import annotations

from indicators.mitigation_filter import MitigationFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class MitigationStrategy(BaseStrategy):
    """
    Bullish Mitigation Block strategy.
    """

    name = "Mitigation"

    def __init__(self) -> None:

        self.mitigation = MitigationFilter()
        self.trend = TrendFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        block = self.mitigation.latest_bullish(
            snapshot,
        )

        if block is None:
            return None

        score = 75

        trend_ok = self.trend.bullish(snapshot)
        volume_ok = self.volume.bullish(snapshot)
        inside = self.mitigation.inside(snapshot)

        if trend_ok:
            score += 10

        if volume_ok:
            score += 10

        if inside:
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
            "Mitigation Block"
        )

        signal.add_reason(
            f"Zone {block.low:.4f} - {block.high:.4f}"
        )

        signal.add_reason(
            f"Distance {self.mitigation.distance_percent(snapshot):.2f}%"
        )

        if inside:

            signal.add_reason(
                "Price inside mitigation block"
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