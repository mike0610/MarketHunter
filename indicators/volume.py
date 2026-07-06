"""
MarketHunter

indicators/volume.py
"""

from __future__ import annotations

from models.candle import Candle


def average_volume(
    candles: list[Candle],
    period: int = 20,
) -> float:
    """
    Average volume for the last N candles.
    """

    if len(candles) < period:
        return 0.0

    window = candles[-period:]

    return (
        sum(c.volume for c in window)
        / period
    )