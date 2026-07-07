"""
MarketHunter

Research Engine

Module:
Research Manager

Version:
0.2
"""

from __future__ import annotations

from uuid import uuid4

from models.signal import Signal
from research.models.trade import ResearchTrade
from research.storage.repository import ResearchRepository


class ResearchManager:
    """
    Creates virtual research trades from trading signals.
    """

    def __init__(
        self,
        repository: ResearchRepository,
    ) -> None:

        self.repository = repository

    def create_from_signal(
        self,
        signal: Signal,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        probability: int,
    ) -> ResearchTrade:

        trade = ResearchTrade(
            id=str(uuid4()),
            signal_id=None,
            symbol=signal.symbol,
            market=signal.market,
            timeframe=signal.timeframe,
            strategy=signal.strategy,
            direction=signal.direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            probability=probability,
            score=signal.score,
            reasons=signal.reasons,
        )

        self.repository.save(trade)

        return trade