"""
MarketHunter

execution/trade_executor.py
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from models.trade_order import TradeOrder
from models.trade_result import TradeResult


class TradeExecutor(ABC):
    """
    Base executor.
    """

    @abstractmethod
    async def execute(
        self,
        order: TradeOrder,
    ) -> TradeResult:
        ...