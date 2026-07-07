"""
MarketHunter

strategies/fvg.py
"""

from __future__ import annotations

from indicators.fvg_filter import FVGFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class FVGStrategy(BaseStrategy):
    """
    Bullish Fair Value Gap strategy.
    """

    name = "FVG"

    def __init__(self) -> None:

        self.trend = TrendFilter()
        self.volume = VolumeFilter()
        self.fvg = FVGFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        gap = self.fvg.latest_bullish(snapshot)

        if gap is None:
            return None

        score = 70

        trend_ok = self.trend.bullish(snapshot)
        volume_ok = self.volume.bullish(snapshot)

        if trend_ok:
            score += 15

        if volume_ok:
            score += 15

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction="LONG",
            score=score,
        )

        signal.add_reason("Bullish Fair Value Gap")

        signal.add_reason(
            f"Gap {gap.lower:.4f} - {gap.upper:.4f}"
        )

        signal.add_reason(
            f"Gap Size {gap.percent:.2f}%"
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