"""
MarketHunter

strategies/choch.py
"""

from __future__ import annotations

from indicators.choch_filter import CHoCHFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class CHoCHStrategy(BaseStrategy):
    """
    Change Of Character strategy.
    """

    name = "CHoCH"

    def __init__(self) -> None:

        self.trend = TrendFilter()
        self.choch = CHoCHFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        #
        # Bullish CHoCH
        #

        if not self.choch.bullish(snapshot):
            return None

        score = 80

        if self.trend.bullish(snapshot):
            score += 10

        if self.volume.bullish(snapshot):
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
            "Change Of Character"
        )

        level = self.choch.bullish_level(
            snapshot,
        )

        if level is not None:

            signal.add_reason(
                f"Swing Low {level:.4f}"
            )

        if self.trend.bullish(snapshot):

            signal.add_reason(
                "Bullish EMA trend"
            )

        if self.volume.bullish(snapshot):

            signal.add_reason(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        return signal