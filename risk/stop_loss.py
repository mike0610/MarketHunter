"""
MarketHunter

risk/stop_loss.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot


class StopLoss:

    def long(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        return snapshot.lowest20 - snapshot.atr14

    def short(
        self,
        snapshot: MarketSnapshot,
    ) -> float:

        return snapshot.highest20 + snapshot.atr14