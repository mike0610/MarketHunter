"""
MarketHunter

scoring/breakout_score.py
"""

from __future__ import annotations

from indicators.atr_filter import ATRFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot


class BreakoutScore:

    def __init__(self) -> None:

        self.trend = TrendFilter()
        self.volume = VolumeFilter()
        self.atr = ATRFilter()

    def calculate(
        self,
        snapshot: MarketSnapshot,
    ) -> tuple[int, list[str]]:

        last = snapshot.candles[-1]

        score = 0
        reasons: list[str] = []

        #
        # Trend
        #

        if not self.trend.bullish(snapshot):
            return 0, []

        score += 25
        reasons.append("Bullish trend")

        #
        # Breakout
        #

        if last.close <= snapshot.highest20:
            return 0, []

        score += 35
        reasons.append("20-day breakout")

        #
        # Volume
        #

        if self.volume.bullish(snapshot):
            score += 20
            reasons.append(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        #
        # ATR
        #

        if self.atr.bullish(snapshot):
            score += 20
            reasons.append(
                f"ATR x{self.atr.ratio(snapshot):.2f}"
            )

        return score, reasons