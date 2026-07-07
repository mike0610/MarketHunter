"""
MarketHunter

scoring/breakout_score.py
"""

from __future__ import annotations

from indicators.atr_filter import ATRFilter
from indicators.bos_filter import BOSFilter
from indicators.breakout_filter import BreakoutFilter
from indicators.liquidity_filter import LiquidityFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot


class BreakoutScore:
    """
    Scores breakout signals using confirmation filters.
    Maximum score: 100
    """

    def __init__(self) -> None:

        self.trend = TrendFilter()
        self.breakout = BreakoutFilter()
        self.bos = BOSFilter()
        self.liquidity = LiquidityFilter()
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
        # Trend (25)
        #

        if not self.trend.bullish(snapshot):
            return 0, []

        score += 25
        reasons.append("Bullish EMA trend")

        #
        # Breakout (30)
        #

        if not self.breakout.bullish(snapshot):
            return 0, []

        score += 30

        reasons.append(
            f"Breakout +{self.breakout.breakout_percent(snapshot):.2f}%"
        )

        #
        # Break Of Structure (15)
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
        # Liquidity Sweep (10)
        #

        if self.liquidity.bullish(snapshot):

            score += 10

            level = self.liquidity.bullish_level(snapshot)

            if level is not None:
                reasons.append(
                    f"Liquidity sweep {level:.4f}"
                )
            else:
                reasons.append("Liquidity sweep")

        #
        # Volume (10)
        #

        if self.volume.bullish(snapshot):

            score += 10

            reasons.append(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        #
        # ATR Impulse (10)
        #

        if self.atr.bullish(snapshot):

            score += 10

            reasons.append(
                f"ATR x{self.atr.ratio(snapshot):.2f}"
            )

        return score, reasons