"""
MarketHunter

models/market_snapshot.py
"""

from __future__ import annotations

from dataclasses import dataclass

from models.candle import Candle


@dataclass(slots=True)
class MarketSnapshot:

    symbol: str

    candles: list[Candle]

    ema20: float
    ema50: float
    ema200: float

    atr14: float

    avg_volume20: float

    highest20: float
    lowest20: float