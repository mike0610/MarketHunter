"""
MarketHunter

risk/risk_manager.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot
from models.risk_result import RiskResult

from risk.position_size import PositionSize
from risk.stop_loss import StopLoss
from risk.take_profit import TakeProfit


class RiskManager:
    """
    Complete risk management.
    """

    def __init__(self) -> None:

        self.position = PositionSize()
        self.stop = StopLoss()
        self.target = TakeProfit()

    def long(
        self,
        snapshot: MarketSnapshot,
        account: float,
        risk_percent: float = 1.0,
        rr: float = 2.0,
    ) -> RiskResult:

        entry = snapshot.candles[-1].close

        stop = self.stop.long(snapshot)

        take = self.target.long(
            entry,
            stop,
            rr,
        )

        size = self.position.calculate(
            account,
            risk_percent,
            entry,
            stop,
        )

        return RiskResult(
            entry=entry,
            stop_loss=stop,
            take_profit=take,
            risk_reward=rr,
            position_size=size,
            risk_amount=account * risk_percent / 100,
            account_size=account,
            risk_percent=risk_percent,
        )

    def short(
        self,
        snapshot: MarketSnapshot,
        account: float,
        risk_percent: float = 1.0,
        rr: float = 2.0,
    ) -> RiskResult:

        entry = snapshot.candles[-1].close

        stop = self.stop.short(snapshot)

        take = self.target.short(
            entry,
            stop,
            rr,
        )

        size = self.position.calculate(
            account,
            risk_percent,
            entry,
            stop,
        )

        return RiskResult(
            entry=entry,
            stop_loss=stop,
            take_profit=take,
            risk_reward=rr,
            position_size=size,
            risk_amount=account * risk_percent / 100,
            account_size=account,
            risk_percent=risk_percent,
        )