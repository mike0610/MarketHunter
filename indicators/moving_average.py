"""
MarketHunter

indicators/moving_average.py
"""

from __future__ import annotations

from models.candle import Candle


def sma(
    candles: list[Candle],
    period: int,
) -> list[float]:
    """
    Simple Moving Average.
    """

    if period <= 0:
        raise ValueError("period must be > 0")

    values: list[float] = []

    for i in range(len(candles)):

        if i + 1 < period:
            values.append(0.0)
            continue

        window = candles[i + 1 - period : i + 1]

        values.append(
            sum(c.close for c in window) / period
        )

    return values


def ema(
    candles: list[Candle],
    period: int,
) -> list[float]:
    """
    Exponential Moving Average.
    """

    if period <= 0:
        raise ValueError("period must be > 0")

    closes = [c.close for c in candles]

    result: list[float] = []

    multiplier = 2 / (period + 1)

    ema_value = closes[0]

    for close in closes:

        ema_value = (
            (close - ema_value) * multiplier
            + ema_value
        )

        result.append(ema_value)

    return result