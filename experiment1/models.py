from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class AccountKind(str, Enum):
    # Legacy single Investments account. Preserved (never removed) so any
    # pre-existing production history under this key stays reachable -
    # STARTING_CASH no longer creates it for fresh deployments; the
    # canonical Investments model is the three independent ledgers below.
    INVESTMENTS = "INVESTMENTS"
    INVESTMENTS_DEFENSIVE = "INVESTMENTS_DEFENSIVE"
    INVESTMENTS_BALANCED = "INVESTMENTS_BALANCED"
    INVESTMENTS_GROWTH = "INVESTMENTS_GROWTH"
    SPOT = "SPOT"
    FUTURES = "FUTURES"


class DecisionAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"
    SHORT = "SHORT"
    WAIT = "WAIT"
    HOLD = "HOLD"


class IntentStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    BLOCKED = "BLOCKED"
    NO_ACTION = "NO_ACTION"


def _nonblank(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-blank")


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OrderIntent:
    intent_id: str
    created_at: datetime
    account: AccountKind
    action: DecisionAction
    symbol: str
    quantity: Decimal
    reason: str
    leverage: Decimal = Decimal("1")
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    def __post_init__(self) -> None:
        _nonblank(self.intent_id, "intent_id")
        _aware(self.created_at, "created_at")
        _nonblank(self.symbol, "symbol")
        _nonblank(self.reason, "reason")
        if self.quantity < 0:
            raise ValueError("quantity must be non-negative")
        if self.leverage <= 0:
            raise ValueError("leverage must be positive")
        if self.action not in (DecisionAction.WAIT, DecisionAction.HOLD) and self.quantity <= 0:
            raise ValueError("trade intents require positive quantity")
        if self.action in (DecisionAction.WAIT, DecisionAction.HOLD) and self.quantity != 0:
            raise ValueError("WAIT/HOLD must use zero quantity")


@dataclass(frozen=True, slots=True)
class MarketQuote:
    symbol: str
    price: Decimal
    observed_at: datetime
    source: str
    source_reference: str
    fee_bps: Decimal
    slippage_bps: Decimal

    def __post_init__(self) -> None:
        _nonblank(self.symbol, "symbol")
        _nonblank(self.source, "source")
        _nonblank(self.source_reference, "source_reference")
        _aware(self.observed_at, "observed_at")
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.fee_bps < 0 or self.slippage_bps < 0:
            raise ValueError("fee_bps/slippage_bps must be non-negative")


@dataclass(frozen=True, slots=True)
class FillRecord:
    intent_id: str
    account: AccountKind
    action: DecisionAction
    symbol: str
    quantity: Decimal
    reference_price: Decimal
    fill_price: Decimal
    fee: Decimal
    leverage: Decimal
    observed_at: datetime
    source: str
    source_reference: str


@dataclass(frozen=True, slots=True)
class AccountState:
    account: AccountKind
    starting_cash: Decimal
    cash: Decimal
    realized_pnl: Decimal
    fees_paid: Decimal
    peak_equity: Decimal
    last_equity: Decimal
    max_drawdown: Decimal
    # cash is the wallet balance - unaffected by margin reservation, only
    # by realized P&L and fees (same semantics for every account kind).
    # used_margin is the sum of initial margin currently reserved across
    # all open Futures-style positions - always 0 for no-leverage accounts,
    # since those pay full cost out of cash at fill time rather than
    # reserving margin separately (see Experiment1Engine.account_state).
    # available_cash = cash - used_margin is what actually gates opening
    # or adding to a Futures position - never cash alone.
    used_margin: Decimal
    available_cash: Decimal


@dataclass(frozen=True, slots=True)
class PositionState:
    account: AccountKind
    symbol: str
    quantity: Decimal
    average_price: Decimal
    leverage: Decimal
    # Initial margin currently reserved for this exact position:
    # abs(quantity) * average_price / leverage. For no-leverage accounts
    # (leverage always 1x) this equals the position's full notional value.
    margin: Decimal

    @property
    def notional(self) -> Decimal:
        return abs(self.quantity) * self.average_price


@dataclass(frozen=True, slots=True)
class ContributionRecord:
    account: AccountKind
    period: str
    amount: Decimal
    applied_at: datetime


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """
    One deterministic round-trip trade (flat -> non-flat -> flat) for one
    symbol in one account, reconstructed from the immutable fills log.
    realized_pnl/fees_paid are exact sums of the authoritative per-fill
    values the engine itself recorded at fill time - never re-derived or
    estimated - so this can never drift from account_state().realized_pnl.
    """

    account: AccountKind
    symbol: str
    opened_at: datetime
    closed_at: datetime
    realized_pnl: Decimal
    fees_paid: Decimal
    fill_count: int
