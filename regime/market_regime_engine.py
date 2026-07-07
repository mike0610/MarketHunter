"""
MarketHunter

regime/market_regime_engine.py
"""

from __future__ import annotations

from models.market_regime import MarketRegime
from models.market_snapshot import MarketSnapshot

from regime.compression_regime import (
    CompressionRegime,
)
from regime.trend_regime import (
    TrendRegime,
)
from regime.volatility_regime import (
    VolatilityRegime,
)


class MarketRegimeEngine:

    def __init__(self):

        self.trend = TrendRegime()
        self.volatility = VolatilityRegime()
        self.compression = CompressionRegime()

    def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> MarketRegime:

        bullish = self.trend.bullish(snapshot)
        bearish = self.trend.bearish(snapshot)

        trend = bullish or bearish

        compression = self.compression.active(
            snapshot,
        )

        expansion = self.volatility.expansion(
            snapshot,
        )

        atr = self.volatility.ratio(
            snapshot,
        )

        ranging = (
            not trend
            and not expansion
        )

        score = 0

        if trend:
            score += 40

        if expansion:
            score += 40

        if not compression:
            score += 20

        if trend and expansion:

            name = "TREND"

        elif expansion:

            name = "EXPANSION"

        elif compression:

            name = "COMPRESSION"

        else:

            name = "RANGE"

        return MarketRegime(
            trend=trend,
            range=ranging,
            compression=compression,
            expansion=expansion,
            volatility=atr,
            atr_ratio=atr,
            name=name,
            score=score,
        )