"""
MarketHunter

models/optimizer_result.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OptimizerResult:
    """
    Optimization result.
    """

    parameters: dict[str, float]

    score: float

    win_rate: float

    profit_factor: float

    drawdown: float

    trades: int