"""
MarketHunter

strategies/compression.py
"""

from __future__ import annotations

from indicators.compression_detector import CompressionDetector
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class CompressionStrategy(BaseStrategy):
    """
    Detects volatility compression.
    """

    name = "Compression"

    def __init__(self) -> None:

        self.trend = TrendFilter()
        self.volume = VolumeFilter()
        self.compression = CompressionDetector()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        if not self.trend.bullish(snapshot):
            return None

        if not self.compression.bullish(
            snapshot.candles
        ):
            return None

        score = 85

        if self.volume.bullish(snapshot):
            score += 15

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction="LONG",
            score=score,
        )

        signal.add_reason("Bullish trend")

        signal.add_reason(
            "Volatility compression"
        )

        signal.add_reason(
            f"Compression {self.compression.strength(snapshot.candles):.1f}%"
        )

        if self.volume.bullish(snapshot):

            signal.add_reason(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        return signal