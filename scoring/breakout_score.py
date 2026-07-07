"""
MarketHunter

scoring/breakout_score.py
"""

from __future__ import annotations

from indicators.atr_filter import ATRFilter
from indicators.bos_filter import BOSFilter
from indicators.breakout_filter import BreakoutFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot


class BreakoutScore:
    """
    Scores breakout signals using multiple confirmation filters.
    """

    def __init__(self) -> None:

        self.trend = TrendFilter()
        self.breakout = BreakoutFilter()
        self.bos = BOSFilter()
        self.volume = VolumeFilter()
        self.atr = ATRFilter()

    def calculate(
        self,
        snapshot: MarketSnapshot,
    ) -> tuple[int, list[str]]:
        """
        Calculate breakout score.
        """

        score = 0
        reasons: list[str] = []

        #
        # Trend
        #

        if not self.trend.bullish(snapshot):
            return 0, []

        score += 25
        reasons.append("Bullish EMA trend")

        #
        # Breakout
        #

        if not self.breakout.bullish(snapshot):
            return 0, []

        score += 35

        reasons.append(
            f"Breakout +{self.breakout.breakout_percent(snapshot):.2f}%"
        )

        #
        # Break Of Structure
        #

        if self.bos.bullish(snapshot):

            score += 15

            level = self.bos.level(snapshot)

            if level is not None:
                reasons.append(
                    f"BOS above {level:.4f}"
                )
            else:
                reasons.append("Bullish BOS")

        #
        # Volume
        #

        if self.volume.bullish(snapshot):

            score += 15

            reasons.append(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        #
        # ATR
        #

        if self.atr.bullish(snapshot):

            score += 10

            reasons.append(
                f"ATR x{self.atr.ratio(snapshot):.2f}"
            )

        return score, reasons