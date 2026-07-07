"""
MarketHunter

models/risk_result.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RiskResult:
    """
    Complete risk calculation.
    """

    entry: float

    stop_loss: float

    take_profit: float

    risk_reward: float

    position_size: float

    risk_amount: float

    account_size: float

    risk_percent: float