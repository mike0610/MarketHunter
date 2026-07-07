"""
MarketHunter

models/backtest_result.py
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BacktestResult:
    """
    Complete backtest statistics.
    """

    initial_balance: float

    final_balance: float

    total_return: float

    trades: int

    wins: int

    losses: int

    win_rate: float

    profit_factor: float

    max_drawdown: float

    sharpe: float

    equity_curve: list[float] = field(
        default_factory=list,
    )