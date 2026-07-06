"""
MarketHunter

strategies/base_strategy.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from models.market_snapshot import MarketSnapshot
from models.signal import Signal


class BaseStrategy(ABC):
    """
    Base strategy interface.
    """

    name: str = "Base"

    @abstractmethod
    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:
        """
        Analyze prepared market snapshot.
        """
        ...