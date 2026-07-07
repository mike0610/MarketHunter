"""
MarketHunter

config/settings.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Settings:

    timeframe: str

    workers: int

    min_candles: int

    account_size: float

    risk_percent: float

    rr: float

    min_score: int

    enable_telegram: bool

    live_trading: bool

    use_testnet: bool