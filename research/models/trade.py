"""
MarketHunter

Module:
Research Trade Model

Responsibilities:
- Store virtual trade state.
- Calculate virtual PnL and R-multiple.
- Track trade lifecycle and candle processing state.
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

    This model never sends orders to Binance or any other exchange.
    It stores how a signal would perform on real market candles.
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
    rr: float = 0.0

    max_profit_percent: float = 0.0
    max_drawdown_percent: float = 0.0

    active_candles: int = 0
    max_active_candles: int = 30
    last_processed_candle_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        """
        Return True while trade waits for entry or is active.
        """

        return self.status in {
            TradeStatus.WAITING_ENTRY,
            TradeStatus.ACTIVE,
        }

    def is_long(self) -> bool:
        """
        Return True for a LONG trade.
        """

        return self.direction.upper() == "LONG"

    def is_short(self) -> bool:
        """
        Return True for a SHORT trade.
        """

        return self.direction.upper() == "SHORT"

    def activate(
        self,
        opened_at: datetime,
    ) -> None:
        """
        Activate the virtual trade at its planned entry price.
        """

        if self.status != TradeStatus.WAITING_ENTRY:
            return

        self.status = TradeStatus.ACTIVE
        self.opened_at = opened_at
        self.last_processed_candle_at = opened_at

    def update_extremes(
        self,
        high: float,
        low: float,
    ) -> None:
        """
        Update maximum favorable and adverse excursion.
        """

        if self.status != TradeStatus.ACTIVE:
            return

        if self.is_long():
            current_profit = (
                (high - self.entry_price)
                / self.entry_price
            ) * 100

            current_drawdown = (
                (low - self.entry_price)
                / self.entry_price
            ) * 100

        else:
            current_profit = (
                (self.entry_price - low)
                / self.entry_price
            ) * 100

            current_drawdown = (
                (self.entry_price - high)
                / self.entry_price
            ) * 100

        self.max_profit_percent = max(
            self.max_profit_percent,
            current_profit,
        )

        self.max_drawdown_percent = min(
            self.max_drawdown_percent,
            current_drawdown,
        )

    def close(
        self,
        price: float,
        reason: str,
        closed_at: datetime,
    ) -> None:
        """
        Close virtual trade and calculate realized PnL.
        """

        if self.status != TradeStatus.ACTIVE:
            return

        self.status = TradeStatus.CLOSED
        self.closed_at = closed_at
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
        closed_at: datetime,
    ) -> None:
        """
        Close an active trade that exceeded its candle lifetime.
        """

        self.close(
            price=price,
            reason="EXPIRED",
            closed_at=closed_at,
        )

        if self.status == TradeStatus.CLOSED:
            self.status = TradeStatus.EXPIRED