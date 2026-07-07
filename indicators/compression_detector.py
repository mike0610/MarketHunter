"""
MarketHunter

indicators/compression_detector.py
"""

from __future__ import annotations

from models.candle import Candle


class CompressionDetector:
    """
    Detects volatility compression.
    """

    def bullish(
        self,
        candles: list[Candle],
        lookback: int = 10,
    ) -> bool:

        if len(candles) < lookback + 10:
            return False

        recent = candles[-lookback:]

        recent_range = sum(
            c.high - c.low
            for c in recent
        ) / lookback

        previous = candles[-(lookback * 2):-lookback]

        previous_range = sum(
            c.high - c.low
            for c in previous
        ) / lookback

        return recent_range < previous_range * 0.7

    def strength(
        self,
        candles: list[Candle],
        lookback: int = 10,
    ) -> float:

        recent = candles[-lookback:]

        previous = candles[-(lookback * 2):-lookback]

        recent_range = sum(
            c.high - c.low
            for c in recent
        ) / lookback

        previous_range = sum(
            c.high - c.low
            for c in previous
        ) / lookback

        if previous_range == 0:
            return 0.0

        return (
            1
            - recent_range / previous_range
        ) * 100