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


class TriggerType(str, Enum):
    """
    A closed, structured set of execution gates MarketHunter can
    objectively evaluate against fresh MarketQuote evidence - never a
    subjective interpretation. Anything not representable by one of
    these (e.g. "confirmed reclaim with continuation evidence") is not
    a valid ExecutionTrigger at all; GIL's own richer context for such
    a condition belongs in GilDecision.execution_condition instead,
    which always fails closed as WAITING_EVIDENCE (see
    experiment1/gil_decision.py) rather than being guessed at.
    """

    IMMEDIATE = "IMMEDIATE"
    PRICE_AT_OR_ABOVE = "PRICE_AT_OR_ABOVE"
    PRICE_AT_OR_BELOW = "PRICE_AT_OR_BELOW"
    PRICE_IN_RANGE = "PRICE_IN_RANGE"


@dataclass(frozen=True, slots=True)
class ExecutionTrigger:
    """
    A structured, deterministic, objectively-evaluable-from-evidence
    execution gate. `note` is an optional free-text annotation GIL can
    attach for human/audit readability only - it is never evaluated or
    interpreted; only trigger_type and the price field(s) it requires
    ever gate execution (see experiment1.gil_decision's evaluation).
    """

    trigger_type: TriggerType
    trigger_price: Decimal | None = None
    trigger_price_low: Decimal | None = None
    trigger_price_high: Decimal | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.trigger_type is TriggerType.IMMEDIATE:
            if self.trigger_price is not None or self.trigger_price_low is not None or self.trigger_price_high is not None:
                raise ValueError("IMMEDIATE trigger must not carry a price")
        elif self.trigger_type in (TriggerType.PRICE_AT_OR_ABOVE, TriggerType.PRICE_AT_OR_BELOW):
            if self.trigger_price is None or self.trigger_price <= 0:
                raise ValueError(f"{self.trigger_type.value} requires a positive trigger_price")
            if self.trigger_price_low is not None or self.trigger_price_high is not None:
                raise ValueError(f"{self.trigger_type.value} must not carry a price range")
        else:  # PRICE_IN_RANGE
            if self.trigger_price_low is None or self.trigger_price_high is None:
                raise ValueError("PRICE_IN_RANGE requires trigger_price_low and trigger_price_high")
            if self.trigger_price_low <= 0 or self.trigger_price_high <= 0:
                raise ValueError("trigger_price_low/trigger_price_high must be positive")
            if self.trigger_price_low >= self.trigger_price_high:
                raise ValueError("trigger_price_low must be less than trigger_price_high")
            if self.trigger_price is not None:
                raise ValueError("PRICE_IN_RANGE must not carry a single trigger_price")
        if self.note is not None:
            _nonblank(self.note, "note")


class SizingMode(str, Enum):
    """GIL's canonical sizing intent, closed and structured - never a guessed quantity."""

    EXACT_QUANTITY = "EXACT_QUANTITY"
    MAX_NOTIONAL = "MAX_NOTIONAL"
    RISK_BUDGET_FROM_STOP = "RISK_BUDGET_FROM_STOP"


@dataclass(frozen=True, slots=True)
class SizingIntent:
    """
    GIL's canonical sizing intent for a decision that does not specify
    a fixed quantity directly. Resolved into a concrete OrderIntent
    quantity only once fresh, approved market evidence exists - see
    experiment1.gil_decision._resolve_quantity. Exactly one of
    exact_quantity/max_notional/risk_budget_amount must be set,
    matching `mode`; MarketHunter never fabricates the others.

    RISK_BUDGET_FROM_STOP requires the decision's own stop_loss (its
    GIL-owned invalidation price) - quantity = risk_budget_amount /
    abs(evidence_price - stop_loss). This is deterministic from
    GIL-supplied fields plus approved market evidence only; it is never
    attempted without both.
    """

    mode: SizingMode
    exact_quantity: Decimal | None = None
    max_notional: Decimal | None = None
    risk_budget_amount: Decimal | None = None

    def __post_init__(self) -> None:
        fields = {
            SizingMode.EXACT_QUANTITY: self.exact_quantity,
            SizingMode.MAX_NOTIONAL: self.max_notional,
            SizingMode.RISK_BUDGET_FROM_STOP: self.risk_budget_amount,
        }
        value = fields[self.mode]
        if value is None or value <= 0:
            raise ValueError(f"{self.mode.value} requires its own positive amount field")
        if any(v is not None for mode, v in fields.items() if mode is not self.mode):
            raise ValueError(f"only the field matching {self.mode.value} may be set")


@dataclass(frozen=True, slots=True)
class GilDecision:
    """
    GIL's own decision, exactly as GIL submits it. GIL owns thesis, the
    action (BUY/WAIT/HOLD/SELL or LONG/SHORT), sizing, invalidation
    (stop_loss/take_profit), and risk parameters (leverage) -
    MarketHunter never manufactures or reinterprets any of these
    fields. account is the ledger GIL is directing this decision into;
    MarketHunter does not choose it on GIL's behalf.

    This is a structured-input-only contract: action must already be a
    decided DecisionAction (BUY/WAIT/HOLD/SELL/LONG/SHORT) - there is no
    free-text parsing anywhere in the ingestion path, so an ambiguous or
    not-yet-decided status (e.g. a research "CANDIDATE") can never be
    coerced into a trade action.

    Sizing is exactly one of two shapes - quantity (a fixed amount GIL
    already decided) XOR sizing (a SizingIntent resolved from fresh
    evidence, e.g. GIL's real sizing is often notional- or risk-budget-
    based, not a pre-computed quantity).

    trigger is an optional ExecutionTrigger - a structured, objectively
    evaluable gate (see TriggerType). Omitted or IMMEDIATE means no
    gating: existing behavior, submitted as soon as risk-validated.

    execution_condition remains the escape hatch for a genuinely
    subjective condition GIL cannot structure (e.g. "confirmed reclaim
    with continuation evidence") - preserved as data only, never
    evaluated, always resolves to WAITING_EVIDENCE (see
    experiment1/gil_decision.py's drain_gil_decision_inbox). It takes
    precedence over trigger if both are somehow present, since it means
    GIL itself flagged this decision as not fully machine-verifiable.

    See experiment1/gil_decision.py for the deterministic mapping into
    the canonical OrderIntent and the MarketHunter risk-validation step
    that follows.
    """

    decision_id: str
    decided_at: datetime
    account: AccountKind
    action: DecisionAction
    symbol: str
    thesis: str
    quantity: Decimal | None = None
    leverage: Decimal = Decimal("1")
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    execution_condition: str | None = None
    trigger: ExecutionTrigger | None = None
    sizing: SizingIntent | None = None

    def __post_init__(self) -> None:
        _nonblank(self.decision_id, "decision_id")
        _nonblank(self.symbol, "symbol")
        _nonblank(self.thesis, "thesis")
        _aware(self.decided_at, "decided_at")
        if self.execution_condition is not None:
            _nonblank(self.execution_condition, "execution_condition")
        if (self.quantity is None) == (self.sizing is None):
            raise ValueError("exactly one of quantity or sizing must be provided")
        if self.sizing is not None and self.sizing.mode is SizingMode.RISK_BUDGET_FROM_STOP and self.stop_loss is None:
            raise ValueError("RISK_BUDGET_FROM_STOP sizing requires stop_loss")


class GilInboxStatus(str, Enum):
    """
    The durable GIL Decision Inbox's own lifecycle for one inbound
    envelope - distinct from IntentStatus, which only exists once an
    envelope has successfully become a GilDecision and been submitted.

    PENDING_DRAIN: durably received, not yet processed by a drain cycle.
    PROCESSED: a drain cycle has run it through ingest_gil_decision (or
    resolved it as WAITING_EVIDENCE for an unverifiable
    execution_condition) - see GilInboxRecord.outcome for the result.
    MALFORMED: the envelope had a decision_id but failed GilDecision's
    own domain validation (e.g. blank thesis, non-aware decided_at) -
    never reaches drain, never becomes an OrderIntent.
    """

    PENDING_DRAIN = "PENDING_DRAIN"
    PROCESSED = "PROCESSED"
    MALFORMED = "MALFORMED"


@dataclass(frozen=True, slots=True)
class GilInboxRecord:
    """One durable GIL Decision Inbox row, for status query/readback."""

    decision_id: str
    received_at: datetime
    status: GilInboxStatus
    outcome: str | None
    outcome_reason: str | None
    intent_id: str | None
    processed_at: datetime | None
