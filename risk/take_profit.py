"""
MarketHunter

risk/take_profit.py
"""

from __future__ import annotations


class TakeProfit:

    def long(
        self,
        entry: float,
        stop: float,
        rr: float = 2.0,
    ) -> float:

        risk = entry - stop

        return entry + risk * rr

    def short(
        self,
        entry: float,
        stop: float,
        rr: float = 2.0,
    ) -> float:

        risk = stop - entry

        return entry - risk * rr