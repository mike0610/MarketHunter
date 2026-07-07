"""
MarketHunter

strategies/false_breakout.py
"""

from __future__ import annotations

from indicators.false_breakout_filter import FalseBreakoutFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class FalseBreakoutStrategy(BaseStrategy):
    """
    False breakout strategy.
    """

    name = "False Breakout"

    def __init__(self) -> None:

        self.trend = TrendFilter()
        self.false_breakout = FalseBreakoutFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        #
        # Trend
        #

        if not self.trend.bullish(snapshot):
            return None

        #
        # False breakout
        #

        if not self.false_breakout.bullish(snapshot):
            return None

        score = 80
        reasons: list[str] = []

        reasons.append("Bullish trend")
        reasons.append("False breakout")

        level = self.false_breakout.bullish_level(snapshot)

        if level is not None:
            reasons.append(
                f"Sweep {level:.4f}"
            )

        if self.volume.bullish(snapshot):

            score += 20

            reasons.append(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction="LONG",
            score=score,
        )

        signal.reasons.extend(reasons)

        return signal