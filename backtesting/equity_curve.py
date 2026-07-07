"""
MarketHunter

backtesting/equity_curve.py
"""

from __future__ import annotations


class EquityCurve:

    def build(
        self,
        balance: float,
        profits: list[float],
    ) -> list[float]:

        curve = [balance]

        current = balance

        for profit in profits:

            current += profit

            curve.append(current)

        return curve