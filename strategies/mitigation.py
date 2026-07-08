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

    MAX_ZONE_DISTANCE_ATR = 1.0
    MAX_ZONE_DISTANCE_PERCENT = 2.0

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
        distance_percent = self.mitigation.distance_percent(
            snapshot,
        )

        if not self._zone_is_close(
            snapshot=snapshot,
            distance_percent=distance_percent,
        ):
            return None

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
            f"Distance {distance_percent:.2f}%"
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

    @classmethod
    def _zone_is_close(
        cls,
        *,
        snapshot: MarketSnapshot,
        distance_percent: float,
    ) -> bool:
        if distance_percent <= 0:
            return True

        if distance_percent > cls.MAX_ZONE_DISTANCE_PERCENT:
            return False

        if (
            snapshot.atr14 <= 0
            or not snapshot.candles
        ):
            return True

        close = snapshot.candles[-1].close

        if close <= 0:
            return True

        distance = close * distance_percent / 100

        return (
            distance / snapshot.atr14
            <= cls.MAX_ZONE_DISTANCE_ATR
        )

