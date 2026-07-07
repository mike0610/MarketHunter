"""
MarketHunter

regime/compression_regime.py
"""

from __future__ import annotations

from indicators.compression_detector import (
    CompressionDetector,
)
from models.market_snapshot import MarketSnapshot


class CompressionRegime:

    def __init__(self):

        self.detector = CompressionDetector()

    def active(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        return self.detector.detect(
            snapshot.candles,
        )