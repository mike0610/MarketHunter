"""
MarketHunter

Research Engine

Performance statistics for virtual trades.
"""

from __future__ import annotations

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus


class ResearchStatistics:
    """
    Calculates transparent performance metrics from virtual trades.
    """

    def calculate(
        self,
        trades: list[ResearchTrade],
    ) -> dict[str, float | int]:
        """
        Return summary statistics for all available trades.
        """

        completed = [
            trade
            for trade in trades
            if trade.status in {
                TradeStatus.CLOSED,
                TradeStatus.EXPIRED,
            }
        ]

        wins = [
            trade
            for trade in completed
            if trade.profit_percent > 0
        ]

        losses = [
            trade
            for trade in completed
            if trade.profit_percent < 0
        ]

        breakeven = [
            trade
            for trade in completed
            if trade.profit_percent == 0
        ]

        gross_profit = sum(
            trade.profit_amount
            for trade in wins
        )

        gross_loss = abs(
            sum(
                trade.profit_amount
                for trade in losses
            )
        )

        decisive_trades = len(wins) + len(losses)

        return {
            "total": len(trades),
            "waiting_entry": sum(
                1
                for trade in trades
                if trade.status == TradeStatus.WAITING_ENTRY
            ),
            "active": sum(
                1
                for trade in trades
                if trade.status == TradeStatus.ACTIVE
            ),
            "completed": len(completed),
            "wins": len(wins),
            "losses": len(losses),
            "breakeven": len(breakeven),
            "win_rate": (
                len(wins)
                / decisive_trades
                * 100
                if decisive_trades > 0
                else 0.0
            ),
            "total_profit": sum(
                trade.profit_amount
                for trade in completed
            ),
            "average_profit": (
                sum(
                    trade.profit_percent
                    for trade in completed
                )
                / len(completed)
                if completed
                else 0.0
            ),
            "average_rr": (
                sum(
                    trade.rr
                    for trade in completed
                )
                / len(completed)
                if completed
                else 0.0
            ),
            "profit_factor": (
                gross_profit
                / gross_loss
                if gross_loss > 0
                else 0.0
            ),
        }