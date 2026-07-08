"""
MarketHunter

indicators/rsi.py

Relative Strength Index indicator.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _close(
    candle: Any,
) -> float:
    return float(candle.close)


def _rsi_value(
    avg_gain: float,
    avg_loss: float,
) -> float:
    if avg_gain == 0 and avg_loss == 0:
        return 50.0

    if avg_loss == 0:
        return 100.0

    if avg_gain == 0:
        return 0.0

    relative_strength = avg_gain / avg_loss

    return 100.0 - (
        100.0 / (1.0 + relative_strength)
    )


def rsi(
    candles: Sequence[Any],
    period: int = 14,
) -> list[float | None]:
    """
    Calculate Wilder RSI.
    """

    if period <= 0:
        raise ValueError(
            "RSI period must be greater than zero."
        )

    closes = [
        _close(candle)
        for candle in candles
    ]

    values: list[float | None] = [
        None
        for _ in closes
    ]

    if len(closes) <= period:
        return values

    gains: list[float] = []
    losses: list[float] = []

    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]

        gains.append(
            max(change, 0.0)
        )

        losses.append(
            max(-change, 0.0)
        )

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    values[period] = _rsi_value(
        avg_gain=avg_gain,
        avg_loss=avg_loss,
    )

    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]

        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        avg_gain = (
            (avg_gain * (period - 1)) + gain
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + loss
        ) / period

        values[index] = _rsi_value(
            avg_gain=avg_gain,
            avg_loss=avg_loss,
        )

    return values
