"""
MarketHunter

models/trade_order.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TradeOrder:
    """
    Order request.
    """

    symbol: str

    market: str

    side: str

    quantity: float

    entry: float

    stop_loss: float

    take_profit: float