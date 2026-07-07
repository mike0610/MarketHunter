"""
MarketHunter

backtesting/metrics.py
"""

from __future__ import annotations


class Metrics:

    def win_rate(
        self,
        profits: list[float],
    ) -> float:

        if not profits:

            return 0

        wins = sum(
            1
            for p in profits
            if p > 0
        )

        return wins / len(profits) * 100

    def profit_factor(
        self,
        profits: list[float],
    ) -> float:

        gross_profit = sum(
            p
            for p in profits
            if p > 0
        )

        gross_loss = abs(

            sum(
                p
                for p in profits
                if p < 0
            )

        )

        if gross_loss == 0:

            return 999

        return gross_profit / gross_loss

    def drawdown(
        self,
        equity: list[float],
    ) -> float:

        peak = equity[0]

        max_dd = 0

        for value in equity:

            if value > peak:

                peak = value

            dd = (
                peak - value
            ) / peak

            max_dd = max(
                max_dd,
                dd,
            )

        return max_dd * 100