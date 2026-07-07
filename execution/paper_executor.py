"""
MarketHunter

execution/paper_executor.py
"""

from __future__ import annotations

import uuid

from models.trade_order import TradeOrder
from models.trade_result import TradeResult

from execution.trade_executor import TradeExecutor


class PaperExecutor(TradeExecutor):
    """
    Paper trading executor.
    """

    async def execute(
        self,
        order: TradeOrder,
    ) -> TradeResult:

        return TradeResult(
            success=True,
            order_id=str(uuid.uuid4()),
            symbol=order.symbol,
            side=order.side,
            price=order.entry,
            quantity=order.quantity,
            message="Paper Trade",
        )