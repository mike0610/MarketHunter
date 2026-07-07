"""
MarketHunter

models/position.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Position:
    """
    Open position.
    """

    symbol: str

    market: str

    side: str

    quantity: float

    entry: float

    stop_loss: float

    take_profit: float

    opened_at: float

    current_price: float

    pnl: float = 0.0

    pnl_percent: float = 0.0

    closed: bool = False

    def update(
        self,
        price: float,
    ) -> None:

        self.current_price = price

        if self.side == "LONG":

            self.pnl = (
                price - self.entry
            ) * self.quantity

            self.pnl_percent = (
                (price - self.entry)
                / self.entry
            ) * 100

        else:

            self.pnl = (
                self.entry - price
            ) * self.quantity

            self.pnl_percent = (
                (self.entry - price)
                / self.entry
            ) * 100