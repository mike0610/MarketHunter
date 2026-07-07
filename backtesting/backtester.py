"""
MarketHunter

backtesting/backtester.py
"""

from __future__ import annotations

from backtesting.equity_curve import (
    EquityCurve,
)
from backtesting.metrics import Metrics
from models.backtest_result import (
    BacktestResult,
)


class Backtester:

    def __init__(self):

        self.metrics = Metrics()

        self.curve = EquityCurve()

    def build_report(
        self,
        initial_balance: float,
        profits: list[float],
    ) -> BacktestResult:

        equity = self.curve.build(
            initial_balance,
            profits,
        )

        final = equity[-1]

        wins = sum(
            1
            for p in profits
            if p > 0
        )

        losses = len(profits) - wins

        return BacktestResult(

            initial_balance=initial_balance,

            final_balance=final,

            total_return=(
                final
                - initial_balance
            )
            / initial_balance
            * 100,

            trades=len(profits),

            wins=wins,

            losses=losses,

            win_rate=self.metrics.win_rate(
                profits,
            ),

            profit_factor=self.metrics.profit_factor(
                profits,
            ),

            max_drawdown=self.metrics.drawdown(
                equity,
            ),

            sharpe=0.0,

            equity_curve=equity,
        )