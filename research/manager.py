"""
MarketHunter

Research Engine

Creates virtual trades from accepted signals.
"""

from __future__ import annotations

from uuid import uuid4

from models.signal import Signal
from research.models.trade import ResearchTrade
from research.storage.repository import ResearchRepository


class ResearchManager:
    """
    Creates and persists virtual trades.

    It does not fetch candles, calculate indicators,
    or execute real exchange orders.
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
        notional: float = 100.0,
    ) -> ResearchTrade | None:
        """
        Create a virtual trade unless an identical open trade exists.
        """

        if notional <= 0:
            raise ValueError(
                "Virtual trade notional must be greater than zero."
            )

        if self.repository.has_open_trade(
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            strategy=signal.strategy,
            direction=signal.direction,
        ):
            return None

        signal_id = signal.metadata.get("signal_id")

        trade = ResearchTrade(
            id=str(uuid4()),
            signal_id=(
                str(signal_id)
                if signal_id is not None
                else None
            ),
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
            notional=notional,
            reasons=list(signal.reasons),
        )

        self.repository.save(trade)

        return trade