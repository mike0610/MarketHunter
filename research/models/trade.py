"""
MarketHunter

research/models/trade.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from research.models.trade_status import TradeStatus


@dataclass(slots=True)
class ResearchTrade:
    id: str
    signal_id: str | None

    symbol: str
    market: str
    timeframe: str
    strategy: str
    direction: str

    entry_price: float
    stop_loss: float
    take_profit: float

    probability: int
    score: float
    reasons: list[str] = field(default_factory=list)

    status: TradeStatus = TradeStatus.WAITING_ENTRY

    created_at: datetime = field(default_factory=datetime.utcnow)
    opened_at: datetime | None = None
    closed_at: datetime | None = None

    close_reason: str | None = None

    profit_amount: float = 0.0
    profit_percent: float = 0.0
    rr: float = 0.0

    max_profit_percent: float = 0.0
    max_drawdown_percent: float = 0.0

    def is_long(self) -> bool:
        return self.direction.upper() == "LONG"

    def is_short(self) -> bool:
        return self.direction.upper() == "SHORT"

    def activate(self) -> None:
        self.status = TradeStatus.ACTIVE
        self.opened_at = datetime.utcnow()

    def close(
        self,
        price: float,
        reason: str,
    ) -> None:

        self.status = TradeStatus.CLOSED
        self.closed_at = datetime.utcnow()
        self.close_reason = reason

        if self.is_long():
            self.profit_percent = (
                (price - self.entry_price)
                / self.entry_price
            ) * 100
        else:
            self.profit_percent = (
                (self.entry_price - price)
                / self.entry_price
            ) * 100

        risk = abs(
            self.entry_price
            - self.stop_loss
        )

        reward = abs(
            price
            - self.entry_price
        )

        if risk > 0:
            self.rr = reward / risk