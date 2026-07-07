"""
MarketHunter

backtesting/report_builder.py
"""

from __future__ import annotations

from models.backtest_result import (
    BacktestResult,
)


class ReportBuilder:

    def print(
        self,
        report: BacktestResult,
    ) -> None:

        print()

        print("=" * 60)

        print("BACKTEST")

        print("=" * 60)

        print(f"Trades        : {report.trades}")

        print(f"Win Rate      : {report.win_rate:.2f}%")

        print(f"Profit Factor : {report.profit_factor:.2f}")

        print(f"Drawdown      : {report.max_drawdown:.2f}%")

        print(f"Return        : {report.total_return:.2f}%")

        print(
            f"Balance       : {report.final_balance:.2f}"
        )