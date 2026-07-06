"""
MarketHunter

services/snapshot_builder.py
"""

from __future__ import annotations

from indicators.atr import atr
from indicators.moving_average import ema
from indicators.volume import average_volume
from models.candle import Candle
from models.market_snapshot import MarketSnapshot


class SnapshotBuilder:
    """
    Builds a MarketSnapshot from historical candles.
    """

    def build(
        self,
        symbol: str,
        candles: list[Candle],
    ) -> MarketSnapshot:
        """
        Calculate indicators once and build a snapshot.
        """

        if len(candles) < 200:
            raise ValueError(
                f"Not enough candles for {symbol}. "
                f"Expected at least 200, got {len(candles)}."
            )

        ema20_values = ema(candles, 20)
        ema50_values = ema(candles, 50)
        ema200_values = ema(candles, 200)

        atr14_values = atr(candles, 14)

        highest20 = max(
            candle.high
            for candle in candles[-21:-1]
        )

        lowest20 = min(
            candle.low
            for candle in candles[-21:-1]
        )

        return MarketSnapshot(
            symbol=symbol,
            candles=candles,
            ema20=ema20_values[-1],
            ema50=ema50_values[-1],
            ema200=ema200_values[-1],
            atr14=atr14_values[-1],
            avg_volume20=average_volume(
                candles[:-1],
                period=20,
            ),
            highest20=highest20,
            lowest20=lowest20,
        )