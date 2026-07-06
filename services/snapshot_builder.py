"""
MarketHunter

services/snapshot_builder.py
"""

from __future__ import annotations

from indicators.atr import atr
from indicators.moving_average import ema
from indicators.support_resistance import SupportResistance
from indicators.volume import average_volume
from models.candle import Candle
from models.market_snapshot import MarketSnapshot


class SnapshotBuilder:
    """
    Builds a MarketSnapshot from historical candles.
    """

    def __init__(self) -> None:
        self.levels = SupportResistance()

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

        ema20 = ema(candles, 20)[-1]
        ema50 = ema(candles, 50)[-1]
        ema200 = ema(candles, 200)[-1]

        atr14 = atr(candles, 14)[-1]

        highest20 = self.levels.resistance(
            candles,
            lookback=20,
        )

        lowest20 = self.levels.support(
            candles,
            lookback=20,
        )

        avg_volume20 = average_volume(
            candles[:-1],
            period=20,
        )

        return MarketSnapshot(
            symbol=symbol,
            candles=candles,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            atr14=atr14,
            avg_volume20=avg_volume20,
            highest20=highest20,
            lowest20=lowest20,
        )