"""
MarketHunter

models/trade_result.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TradeResult:
    """
    Order execution result.
    """

    success: bool

    order_id: str

    symbol: str

    side: str

    price: float

    quantity: float

    message: str = ""