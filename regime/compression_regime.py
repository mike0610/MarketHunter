"""
MarketHunter

Module:
Compression Regime

Responsibilities:
- Determine whether current market conditions are compressed.
- Delegate compression detection to CompressionDetector.
"""

from __future__ import annotations

from indicators.compression_detector import (
    CompressionDetector,
)
from models.market_snapshot import MarketSnapshot


class CompressionRegime:
    """
    Determines whether the market is currently in compression.
    """

    def __init__(self) -> None:
        self.detector = CompressionDetector()

    def active(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:
        """
        Return True when the current candles show volatility compression.
        """

        return self.detector.bullish(
            snapshot.candles,
        )