"""
MarketHunter

reporting/statistics_report.py
"""

from __future__ import annotations


class StatisticsReport:

    def save(
        self,
        result,
        filename: str,
    ) -> None:

        with open(
            filename,
            "w",
            encoding="utf8",
        ) as file:

            file.write(
                "MarketHunter Report\n\n"
            )

            file.write(
                f"Trades: {result.trades}\n"
            )

            file.write(
                f"Wins: {result.wins}\n"
            )

            file.write(
                f"Losses: {result.losses}\n"
            )

            file.write(
                f"Win Rate: {result.win_rate:.2f}%\n"
            )

            file.write(
                f"Profit Factor: {result.profit_factor:.2f}\n"
            )

            file.write(
                f"Drawdown: {result.max_drawdown:.2f}%\n"
            )

            file.write(
                f"Return: {result.total_return:.2f}%\n"
            )
            