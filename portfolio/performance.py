"""
MarketHunter

portfolio/performance.py
"""

from __future__ import annotations

from models.portfolio import Portfolio


class Performance:

    def win_rate(
        self,
        portfolio: Portfolio,
    ) -> float:

        closed = [
            p
            for p in portfolio.positions
            if p.closed
        ]

        if not closed:
            return 0.0

        wins = sum(
            1
            for p in closed
            if p.pnl > 0
        )

        return (
            wins
            / len(closed)
            * 100
        )

    def total_profit(
        self,
        portfolio: Portfolio,
    ) -> float:

        return (
            portfolio.closed_profit
            + portfolio.open_profit
        )