"""Immutable input contracts for GIL Experiment 1.

This module deliberately stops at intent/account semantics. It does not fetch
market data, create fills, mutate live trading state, or invent execution
mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class ExperimentAccountKind(str, Enum):
    INVESTMENTS = "investments"
    SPOT = "spot"
    FUTURES = "futures"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderIntentStatus(str, Enum):
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    WAITING_MARKET = "WAITING_MARKET"
    READY_FOR_PAPER_FILL = "READY_FOR_PAPER_FILL"
    PAPER_FILLED = "PAPER_FILLED"
    CANCELLED = "CANCELLED"


def _nonblank(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-blank")


def _positive(value: Decimal | None, field: str) -> None:
    if value is not None and (not isinstance(value, Decimal) or value <= 0):
        raise ValueError(f"{field} must be a positive Decimal when supplied")


@dataclass(frozen=True, slots=True)
class ExperimentAccount:
    account_id: str
    portfolio_id: str
    kind: ExperimentAccountKind
    starting_cash: Decimal
    leverage_allowed: bool

    def __post_init__(self) -> None:
        _nonblank(self.account_id, "account_id")
        _nonblank(self.portfolio_id, "portfolio_id")
        _positive(self.starting_cash, "starting_cash")
        if self.kind is not ExperimentAccountKind.FUTURES and self.leverage_allowed:
            raise ValueError("leverage is allowed only for the futures account")


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """One caller-owned decision offered to the paper engine.

    `intent_id` is the idempotency key. Quantity and target_notional are
    mutually exclusive sizing instructions. No fill price, fee, slippage or
    funding value exists here because those must come from governed evidence.
    """

    intent_id: str
    account_id: str
    portfolio_id: str
    strategy_id: str
    instrument_id: str
    asset_class: str
    side: OrderSide
    order_type: OrderType
    created_at: datetime
    quantity: Decimal | None = None
    target_notional: Decimal | None = None
    limit_price: Decimal | None = None
    trigger_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    time_in_force: str | None = None
    thesis: str | None = None
    invalidation: str | None = None
    max_risk: Decimal | None = None
    leverage_limit: Decimal | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.intent_id, "intent_id"),
            (self.account_id, "account_id"),
            (self.portfolio_id, "portfolio_id"),
            (self.strategy_id, "strategy_id"),
            (self.instrument_id, "instrument_id"),
            (self.asset_class, "asset_class"),
        ):
            _nonblank(value, field)

        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

        if (self.quantity is None) == (self.target_notional is None):
            raise ValueError("supply exactly one of quantity or target_notional")

        for value, field in (
            (self.quantity, "quantity"),
            (self.target_notional, "target_notional"),
            (self.limit_price, "limit_price"),
            (self.trigger_price, "trigger_price"),
            (self.stop_loss, "stop_loss"),
            (self.take_profit, "take_profit"),
            (self.max_risk, "max_risk"),
            (self.leverage_limit, "leverage_limit"),
        ):
            _positive(value, field)

        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT intent requires limit_price")
        if self.order_type is OrderType.STOP and self.trigger_price is None:
            raise ValueError("STOP intent requires trigger_price")
