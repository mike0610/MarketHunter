"""
MarketHunter

portfolio/portfolio_manager.py
"""

from __future__ import annotations

from models.portfolio import Portfolio
from models.position import Position


class PortfolioManager:
    """
    Portfolio manager.
    """

    def __init__(
        self,
        initial_balance: float,
    ) -> None:

        self.portfolio = Portfolio(

            balance=initial_balance,

            equity=initial_balance,

        )

    def add_position(
        self,
        position: Position,
    ) -> None:

        self.portfolio.positions.append(
            position,
        )

    def update_price(
        self,
        symbol: str,
        price: float,
    ) -> None:

        for position in self.portfolio.positions:

            if (
                position.symbol == symbol
                and not position.closed
            ):

                position.update(
                    price,
                )

        self.portfolio.equity = (

            self.portfolio.balance

            + self.portfolio.open_profit

        )

    def close_position(
        self,
        symbol: str,
        price: float,
    ) -> None:

        for position in self.portfolio.positions:

            if (
                position.symbol == symbol
                and not position.closed
            ):

                position.update(
                    price,
                )

                position.closed = True

                self.portfolio.balance += (
                    position.pnl
                )

                self.portfolio.closed_profit += (
                    position.pnl
                )

        self.portfolio.equity = (
            self.portfolio.balance
        )

    def open_positions(
        self,
    ) -> list[Position]:

        return [

            p

            for p in self.portfolio.positions

            if not p.closed

        ]

    def closed_positions(
        self,
    ) -> list[Position]:

        return [

            p

            for p in self.portfolio.positions

            if p.closed

        ]