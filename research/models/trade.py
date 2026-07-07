"""
MarketHunter

Research Engine

Virtual research trade model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from research.models.trade_status import TradeStatus


def utc_now() -> datetime:
    """
    Return timezone-aware UTC datetime.
    """

    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ResearchTrade:
    """
    Virtual trade created from a MarketHunter signal.

    The trade never sends an order to an exchange.
    It only tracks how the idea would perform on real market data.
    """

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

    notional: float = 100.0
    reasons: list[str] = field(default_factory=list)

    status: TradeStatus = TradeStatus.WAITING_ENTRY

    created_at: datetime = field(default_factory=utc_now)
    opened_at: datetime | None = None
    closed_at: datetime | None = None

    close_reason: str | None = None

    profit_amount: float = 0.0
    profit_percent: float = 0.0

    # Realized result in R-multiples.
    # Example: TP at 2R => rr = 2.0; SL => rr = -1.0.
    rr: float = 0.0

    max_profit_percent: float = 0.0
    max_drawdown_percent: float = 0.0

    @property
    def is_open(self) -> bool:
        """
        Return True while the trade is waiting for entry or active.
        """

        return self.status in {
            TradeStatus.WAITING_ENTRY,
            TradeStatus.ACTIVE,
        }

    def is_long(self) -> bool:
        """
        Return True for LONG trade.
        """

        return self.direction.upper() == "LONG"

    def is_short(self) -> bool:
        """
        Return True for SHORT trade.
        """

        return self.direction.upper() == "SHORT"

    def activate(
        self,
        opened_at: datetime | None = None,
    ) -> None:
        """
        Activate a trade after market price reaches entry.
        """

        self.status = TradeStatus.ACTIVE
        self.opened_at = opened_at or utc_now()

    def update_extremes(
        self,
        high: float,
        low: float,
    ) -> None:
        """
        Track best and worst excursion while the trade is active.
        """

        if self.status != TradeStatus.ACTIVE:
            return

        if self.is_long():
            max_profit = (
                (high - self.entry_price)
                / self.entry_price
            ) * 100

            max_drawdown = (
                (low - self.entry_price)
                / self.entry_price
            ) * 100

        else:
            max_profit = (
                (self.entry_price - low)
                / self.entry_price
            ) * 100

            max_drawdown = (
                (self.entry_price - high)
                / self.entry_price
            ) * 100

        self.max_profit_percent = max(
            self.max_profit_percent,
            max_profit,
        )

        self.max_drawdown_percent = min(
            self.max_drawdown_percent,
            max_drawdown,
        )

    def close(
        self,
        price: float,
        reason: str,
        closed_at: datetime | None = None,
    ) -> None:
        """
        Close trade at a virtual price and calculate final result.
        """

        self.status = TradeStatus.CLOSED
        self.closed_at = closed_at or utc_now()
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

        self.profit_amount = (
            self.notional
            * self.profit_percent
            / 100
        )

        risk_percent = (
            abs(self.entry_price - self.stop_loss)
            / self.entry_price
        ) * 100

        if risk_percent > 0:
            self.rr = (
                self.profit_percent
                / risk_percent
            )

    def expire(
        self,
        price: float,
        closed_at: datetime | None = None,
    ) -> None:
        """
        Mark a trade as expired when it did not hit TP or SL in time.
        """

        self.close(
            price=price,
            reason="EXPIRED",
            closed_at=closed_at,
        )

        self.status = TradeStatus.EXPIRED