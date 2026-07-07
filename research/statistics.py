"""
MarketHunter

Research Engine

Module:
Research Statistics

Version:
0.2
"""

from __future__ import annotations

import sqlite3


class ResearchStatistics:
    """
    Calculates statistics for virtual research trades.
    """

    def calculate(
        self,
        trades: list[sqlite3.Row],
    ) -> dict:

        total = len(trades)

        if total == 0:
            return {
                "total": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "average_profit": 0.0,
                "profit_factor": 0.0,
            }

        wins = [
            trade
            for trade in trades
            if trade["profit_percent"] > 0
        ]

        losses = [
            trade
            for trade in trades
            if trade["profit_percent"] < 0
        ]

        gross_profit = sum(
            trade["profit_percent"]
            for trade in wins
        )

        gross_loss = abs(
            sum(
                trade["profit_percent"]
                for trade in losses
            )
        )

        return {
            "total": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / total * 100,
            "average_profit": sum(
                trade["profit_percent"]
                for trade in trades
            ) / total,
            "profit_factor": (
                gross_profit / gross_loss
                if gross_loss > 0
                else 0.0
            ),
        }