"""
MarketHunter

indicators/atr.py
"""

from __future__ import annotations

from models.candle import Candle


def atr(
    candles: list[Candle],
    period: int = 14,
) -> list[float]:
    """
    Average True Range.
    """

    if len(candles) < period + 1:
        return []

    true_ranges: list[float] = []

    for i in range(1, len(candles)):

        current = candles[i]
        previous = candles[i - 1]

        tr = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )

        true_ranges.append(tr)

    result: list[float] = []

    for i in range(len(true_ranges)):

        if i + 1 < period:
            result.append(0.0)
            continue

        window = true_ranges[i + 1 - period:i + 1]

        result.append(sum(window) / period)

    return result