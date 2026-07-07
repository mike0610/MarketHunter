"""
MarketHunter

models/portfolio.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

from models.position import Position


@dataclass(slots=True)
class Portfolio:
    """
    Portfolio state.
    """

    balance: float

    equity: float

    positions: list[Position] = field(
        default_factory=list,
    )

    closed_profit: float = 0.0

    @property
    def open_profit(
        self,
    ) -> float:

        return sum(
            p.pnl
            for p in self.positions
            if not p.closed
        )