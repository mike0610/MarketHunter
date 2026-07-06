"""
MarketHunter

scoring/breakout_score.py
"""

from __future__ import annotations

from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot


class BreakoutScore:

    def __init__(self) -> None:

        self.trend = TrendFilter()
        self.volume = VolumeFilter()

    def calculate(
        self,
        snapshot: MarketSnapshot,
    ) -> tuple[int, list[str]]:

        last = snapshot.candles[-1]

        score = 0
        reasons: list[str] = []

        if not self.trend.bullish(snapshot):
            return 0, []

        score += 25
        reasons.append("Bullish trend")

        if last.close <= snapshot.highest20:
            return 0, []

        score += 35
        reasons.append("20-day breakout")

        if self.volume.bullish(snapshot):
            score += 20
            reasons.append(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        if last.body > snapshot.atr14:
            score += 20
            reasons.append("ATR impulse")

        return score, reasons