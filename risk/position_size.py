"""
MarketHunter

risk/position_size.py
"""

from __future__ import annotations


class PositionSize:

    def calculate(
        self,
        account: float,
        risk_percent: float,
        entry: float,
        stop: float,
    ) -> float:

        risk_amount = account * risk_percent / 100

        distance = abs(entry - stop)

        if distance <= 0:

            return 0.0

        return risk_amount / distance