"""
MarketHunter

regime/volatility_regime.py
"""

from __future__ import annotations

from indicators.atr_filter import ATRFilter
from models.market_snapshot import MarketSnapshot


class VolatilityRegime:

    def __init__(self):

        self.atr = ATRFilter()

    def ratio(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        return self.atr.ratio(snapshot)

    def expansion(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        return self.ratio(snapshot) >= 1.30

    def compression(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:

        return self.ratio(snapshot) <= 0.80