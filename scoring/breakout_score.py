"""
MarketHunter

scoring/breakout_score.py
"""

from __future__ import annotations

from indicators.trend import TrendFilter
from models.market_snapshot import MarketSnapshot


class BreakoutScore:

    def __init__(self) -> None:
        self.trend = TrendFilter()

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

        if self.trend.bullish(snapshot):
            score += 25
            reasons.append("Bullish EMA trend")
        else:
            return 0, []

        #
        # Breakout
        #

        if last.close > snapshot.highest20:
            score += 35
            reasons.append("20-day breakout")
        else:
            return 0, []

        #
        # Volume
        #

        if last.volume > snapshot.avg_volume20 * 1.5:
            score += 20
            reasons.append("Volume ×1.5")

        #
        # ATR
        #

        if last.body > snapshot.atr14:
            score += 20
            reasons.append("ATR impulse")

        return score, reasons