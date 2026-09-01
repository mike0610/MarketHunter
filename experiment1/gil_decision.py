from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import (
    AccountKind,
    DecisionAction,
    ExecutionTrigger,
    GilDecision,
    IntentStatus,
    OrderIntent,
    SizingIntent,
    SizingMode,
    TriggerType,
)
from experiment1.runtime import AsyncQuoteSource


_INTENT_ID_PREFIX = "gil-decision:"


def intent_id_for(decision_id: str) -> str:
    """
    Deterministic, stable mapping from a GIL decision_id to its
    MarketHunter intent_id. This is the full audit provenance trail
    back to the originating GIL decision: given only an intent_id,
    decision_id_from() recovers the exact GIL decision that produced
    it, with no separate lookup table needed. Also the source of this
    contract's idempotency - the same decision_id always maps to the
    same intent_id, and Experiment1Engine.submit_intent() is already
    idempotent on an identical resubmission of the same intent_id.
    """
    if not decision_id or not decision_id.strip():
        raise ValueError("decision_id must be non-blank")
    return f"{_INTENT_ID_PREFIX}{decision_id}"


def decision_id_from(intent_id: str) -> str | None:
    """Inverse of intent_id_for. None if intent_id was not GIL-originated."""
    if not intent_id.startswith(_INTENT_ID_PREFIX):
        return None
    return intent_id[len(_INTENT_ID_PREFIX):]


def to_order_intent(
    decision: GilDecision, *, resolved_quantity: Decimal | None = None, sizing_note: str | None = None
) -> OrderIntent:
    """
    Deterministic, lossless mapping from a GIL Decision to the existing
    canonical OrderIntent. Every GIL-owned field - action, symbol,
    leverage, stop_loss, take_profit - is copied verbatim, never
    defaulted or reinterpreted by MarketHunter. Quantity is
    `decision.quantity` unless `resolved_quantity` overrides it (used
    when GIL's own sizing intent required deriving a quantity from
    fresh evidence - see _resolve_quantity); `sizing_note`, if given,
    is appended to `reason` for audit readability. `reason` also
    carries GIL's own thesis text plus the decision_id for
    human-readable audit; intent_id carries the same provenance
    structurally (see intent_id_for/decision_id_from).
    """
    quantity = decision.quantity if resolved_quantity is None else resolved_quantity
    reason = f"GIL decision {decision.decision_id}: {decision.thesis}"
    if sizing_note:
        reason = f"{reason} ({sizing_note})"
    return OrderIntent(
        intent_id=intent_id_for(decision.decision_id),
        created_at=decision.decided_at,
        account=decision.account,
        action=decision.action,
        symbol=decision.symbol,
        quantity=quantity,
        reason=reason,
        leverage=decision.leverage,
        stop_loss=decision.stop_loss,
        take_profit=decision.take_profit,
    )


def ingest_gil_decision(
    engine: Experiment1Engine,
    decision: GilDecision,
    *,
    resolved_quantity: Decimal | None = None,
    sizing_note: str | None = None,
) -> IntentStatus:
    """
    The GIL Decision -> canonical OrderIntent -> MarketHunter
    risk-validation contract. Maps `decision` deterministically to an
    OrderIntent (see to_order_intent) and submits it through the
    engine's own existing submit_intent() - the exact same account/
    leverage policy validation every other intent goes through, never
    bypassed or duplicated here. A policy rejection is persisted as an
    auditable BLOCKED row with its exact reason by submit_intent's own
    existing contract, and - matching that same contract exactly -
    this function still raises Experiment1Error for a NEW rejection
    (the caller decides whether to continue past it, same as any other
    submit_intent() call); resubmitting an already-recorded decision
    (accepted or blocked) returns its recorded status without raising.

    A decision that specifies GilDecision.sizing (rather than a fixed
    quantity) cannot be ingested directly here - its quantity can only
    be derived from fresh market evidence, which only
    drain_gil_decision_inbox has access to. Callers with sizing-based
    decisions and an already-resolved quantity should pass
    resolved_quantity explicitly.

    Idempotent and restart-safe by construction: intent_id is
    deterministic from decision.decision_id, and submit_intent() is
    already idempotent on identical resubmission - so replaying the
    exact same GilDecision, including after a process restart over the
    same db file, returns the same recorded status without duplicating
    anything.

    This function ONLY submits the intent - it never calls
    execute_pending. Execution, monitoring/SL/TP, exits, and statistics
    continue through the existing, unmodified paper lifecycle
    (run_market_cycle, run_protective_exit_cycle, closed_trades) -
    there is no parallel execution path.
    """
    if resolved_quantity is None and decision.quantity is None:
        raise Experiment1Error(
            "decision uses structured sizing - quantity must be resolved from fresh evidence "
            "via drain_gil_decision_inbox, not ingested directly"
        )
    return engine.submit_intent(to_order_intent(decision, resolved_quantity=resolved_quantity, sizing_note=sizing_note))


@dataclass(frozen=True, slots=True)
class GilIngestionResult:
    decision_id: str
    intent_id: str
    outcome: str  # IntentStatus value, "BLOCKED", or "WAITING_EVIDENCE"
    detail: str | None = None


def run_gil_ingestion_cycle(
    engine: Experiment1Engine, decisions: Iterable[GilDecision]
) -> tuple[GilIngestionResult, ...]:
    """
    Ingest a batch of already-fully-specified (fixed-quantity) GIL
    decisions, catching a per-decision policy rejection rather than
    aborting the whole batch - the same catch-and-report shape already
    used by run_market_cycle and run_protective_exit_cycle for their
    own per-item iteration. A sizing-based decision belongs in the
    durable inbox (drain_gil_decision_inbox), not here.
    """
    results: list[GilIngestionResult] = []
    for decision in decisions:
        intent_id = intent_id_for(decision.decision_id)
        try:
            status = ingest_gil_decision(engine, decision)
            results.append(GilIngestionResult(decision.decision_id, intent_id, status.value))
        except Experiment1Error as exc:
            results.append(GilIngestionResult(decision.decision_id, intent_id, "BLOCKED", detail=str(exc)))
    return tuple(results)


def decision_to_json(decision: GilDecision) -> str:
    """
    The GIL Decision Inbox's own canonical, explicit serialization -
    deliberately independent of any web-framework's default JSON
    encoding so the stored envelope's exact bytes are predictable and
    round-trip losslessly through decision_from_json. Used both as the
    idempotency-comparison key for a resubmitted decision_id and as
    what a drain cycle reconstructs a GilDecision from.
    """
    return json.dumps(
        {
            "decision_id": decision.decision_id,
            "decided_at": decision.decided_at.isoformat(),
            "account": decision.account.value,
            "action": decision.action.value,
            "symbol": decision.symbol,
            "thesis": decision.thesis,
            "quantity": None if decision.quantity is None else str(decision.quantity),
            "leverage": str(decision.leverage),
            "stop_loss": None if decision.stop_loss is None else str(decision.stop_loss),
            "take_profit": None if decision.take_profit is None else str(decision.take_profit),
            "execution_condition": decision.execution_condition,
            "trigger": _trigger_to_dict(decision.trigger),
            "sizing": _sizing_to_dict(decision.sizing),
        },
        sort_keys=True,
    )


def _trigger_to_dict(trigger: ExecutionTrigger | None) -> dict | None:
    if trigger is None:
        return None
    return {
        "trigger_type": trigger.trigger_type.value,
        "trigger_price": None if trigger.trigger_price is None else str(trigger.trigger_price),
        "trigger_price_low": None if trigger.trigger_price_low is None else str(trigger.trigger_price_low),
        "trigger_price_high": None if trigger.trigger_price_high is None else str(trigger.trigger_price_high),
        "note": trigger.note,
    }


def _sizing_to_dict(sizing: SizingIntent | None) -> dict | None:
    if sizing is None:
        return None
    return {
        "mode": sizing.mode.value,
        "exact_quantity": None if sizing.exact_quantity is None else str(sizing.exact_quantity),
        "max_notional": None if sizing.max_notional is None else str(sizing.max_notional),
        "risk_budget_amount": None if sizing.risk_budget_amount is None else str(sizing.risk_budget_amount),
    }


def decision_from_json(raw: str) -> GilDecision:
    """Inverse of decision_to_json."""
    data = json.loads(raw)
    trigger_data = data.get("trigger")
    trigger = None
    if trigger_data is not None:
        trigger = ExecutionTrigger(
            trigger_type=TriggerType(trigger_data["trigger_type"]),
            trigger_price=None if trigger_data["trigger_price"] is None else Decimal(trigger_data["trigger_price"]),
            trigger_price_low=None
            if trigger_data["trigger_price_low"] is None
            else Decimal(trigger_data["trigger_price_low"]),
            trigger_price_high=None
            if trigger_data["trigger_price_high"] is None
            else Decimal(trigger_data["trigger_price_high"]),
            note=trigger_data["note"],
        )
    sizing_data = data.get("sizing")
    sizing = None
    if sizing_data is not None:
        sizing = SizingIntent(
            mode=SizingMode(sizing_data["mode"]),
            exact_quantity=None if sizing_data["exact_quantity"] is None else Decimal(sizing_data["exact_quantity"]),
            max_notional=None if sizing_data["max_notional"] is None else Decimal(sizing_data["max_notional"]),
            risk_budget_amount=None
            if sizing_data["risk_budget_amount"] is None
            else Decimal(sizing_data["risk_budget_amount"]),
        )
    return GilDecision(
        decision_id=data["decision_id"],
        decided_at=datetime.fromisoformat(data["decided_at"]),
        account=AccountKind(data["account"]),
        action=DecisionAction(data["action"]),
        symbol=data["symbol"],
        thesis=data["thesis"],
        quantity=None if data["quantity"] is None else Decimal(data["quantity"]),
        leverage=Decimal(data["leverage"]),
        stop_loss=None if data["stop_loss"] is None else Decimal(data["stop_loss"]),
        take_profit=None if data["take_profit"] is None else Decimal(data["take_profit"]),
        execution_condition=data.get("execution_condition"),
        trigger=trigger,
        sizing=sizing,
    )


_NO_EVALUATOR_REASON = (
    "execution_condition is present but no evaluator exists in this environment that can "
    "objectively verify an arbitrary condition against market evidence - failing closed as "
    "WAITING_EVIDENCE rather than guessing"
)


def _trigger_satisfied(trigger: ExecutionTrigger, price: Decimal) -> bool:
    if trigger.trigger_type is TriggerType.IMMEDIATE:
        return True
    if trigger.trigger_type is TriggerType.PRICE_AT_OR_ABOVE:
        return price >= trigger.trigger_price
    if trigger.trigger_type is TriggerType.PRICE_AT_OR_BELOW:
        return price <= trigger.trigger_price
    return trigger.trigger_price_low <= price <= trigger.trigger_price_high


def _resolve_quantity(decision: GilDecision, price: Decimal | None) -> tuple[Decimal | None, str]:
    """
    Deterministically resolve GilDecision.sizing into a concrete
    quantity from `price` (fresh, approved market evidence) plus only
    GIL-owned fields already on the decision. Returns (None, reason)
    when resolution genuinely cannot be done without fabricating a
    value - never a guessed fallback. `price` is only required for
    MAX_NOTIONAL/RISK_BUDGET_FROM_STOP - EXACT_QUANTITY never needs it.
    """
    sizing = decision.sizing
    if sizing.mode is SizingMode.EXACT_QUANTITY:
        return sizing.exact_quantity, f"sizing EXACT_QUANTITY={sizing.exact_quantity}"
    if sizing.mode is SizingMode.MAX_NOTIONAL:
        quantity = sizing.max_notional / price
        return quantity, f"sizing MAX_NOTIONAL={sizing.max_notional} @ price={price} -> quantity={quantity}"
    # RISK_BUDGET_FROM_STOP - GilDecision.__post_init__ already guarantees stop_loss is set.
    distance = abs(price - decision.stop_loss)
    if distance == 0:
        return None, (
            f"sizing RISK_BUDGET_FROM_STOP cannot resolve: evidence price {price} equals "
            f"stop_loss {decision.stop_loss} (zero stop distance)"
        )
    quantity = sizing.risk_budget_amount / distance
    return quantity, (
        f"sizing RISK_BUDGET_FROM_STOP={sizing.risk_budget_amount} @ price={price} "
        f"stop_loss={decision.stop_loss} distance={distance} -> quantity={quantity}"
    )


def _observation_intent(account: AccountKind, symbol: str, now: datetime) -> OrderIntent:
    """
    A WAIT/zero-quantity carrier object that exists only to satisfy the
    AsyncQuoteSource.quote_for(intent) contract (it reads intent.symbol
    and intent.account only - see BinanceExperiment1QuoteSource). Never
    submitted to the engine, never a trade decision.
    """
    return OrderIntent(
        intent_id=f"gil-drain-observe:{account.value}:{symbol}",
        created_at=now,
        account=account,
        action=DecisionAction.WAIT,
        symbol=symbol,
        quantity=Decimal("0"),
        reason="GIL decision trigger/sizing evaluation - observation only, never submitted to the engine",
    )


async def drain_gil_decision_inbox(
    engine: Experiment1Engine, quote_source: AsyncQuoteSource
) -> tuple[GilIngestionResult, ...]:
    """
    Process every envelope still PENDING_DRAIN in the durable GIL
    Decision Inbox (see Experiment1Engine.receive_gil_decision) - the
    "no manual operator step" automatic drain a runtime scheduler cycle
    calls instead of ever passing an empty or manufactured decision
    batch to run_gil_ingestion_cycle.

    A decision carrying a non-blank execution_condition is never
    guessed into an executable order: there is no evaluator anywhere in
    this codebase that can objectively verify an arbitrary condition
    against approved market evidence, so it is marked WAITING_EVIDENCE
    (terminal - PROCESSED) directly, with the condition itself
    preserved in the inbox row - never submitted to ingest_gil_decision.

    A decision carrying a structured ExecutionTrigger (see TriggerType)
    and/or a sizing mode that needs fresh evidence (MAX_NOTIONAL,
    RISK_BUDGET_FROM_STOP) requires a live quote for its symbol this
    cycle. If the trigger is not yet satisfied, the quote is missing/
    stale/unsupported, or sizing genuinely cannot be resolved (e.g. zero
    stop distance), the envelope STAYS PENDING_DRAIN (never marked
    PROCESSED) with an updated outcome_reason explaining why - it
    remains watchable and is re-evaluated on the next drain cycle,
    exactly until it resolves. This cycle's own result for that
    envelope is still reported as WAITING_EVIDENCE.

    Every decision that does resolve (trigger satisfied or immediate,
    quantity known or derived) goes through the exact same
    ingest_gil_decision path as a directly ingested one - same risk
    validation, same BLOCKED-persistence contract, same idempotency.

    Idempotent and restart-safe: only PENDING_DRAIN rows are selected,
    so re-running drain (including after a process restart) never
    reprocesses an already-PROCESSED or MALFORMED envelope, and
    ingest_gil_decision's own idempotency covers the case where a crash
    happens after ingestion but before the row is marked PROCESSED.
    """
    results: list[GilIngestionResult] = []
    for decision_id, raw_payload in engine.pending_gil_decision_inbox():
        decision = decision_from_json(raw_payload)
        intent_id = intent_id_for(decision.decision_id)

        if decision.execution_condition is not None:
            engine.mark_gil_decision_processed(
                decision_id, outcome="WAITING_EVIDENCE", outcome_reason=_NO_EVALUATOR_REASON, intent_id=intent_id
            )
            results.append(
                GilIngestionResult(decision_id, intent_id, "WAITING_EVIDENCE", detail=_NO_EVALUATOR_REASON)
            )
            continue

        gated_by_trigger = decision.trigger is not None and decision.trigger.trigger_type is not TriggerType.IMMEDIATE
        gated_by_sizing = decision.sizing is not None and decision.sizing.mode is not SizingMode.EXACT_QUANTITY
        needs_quote = gated_by_trigger or gated_by_sizing

        price: Decimal | None = None
        if needs_quote:
            observation = _observation_intent(decision.account, decision.symbol, datetime.now(timezone.utc))
            try:
                quote = await quote_source.quote_for(observation)
            except Exception as exc:
                reason = f"quote lookup failed for {decision.symbol}: {exc}"
                engine.record_gil_decision_watch(decision_id, reason)
                results.append(GilIngestionResult(decision_id, intent_id, "WAITING_EVIDENCE", detail=reason))
                continue
            if quote is None:
                reason = f"no fresh quote available for {decision.symbol} - stale, missing, or unsupported"
                engine.record_gil_decision_watch(decision_id, reason)
                results.append(GilIngestionResult(decision_id, intent_id, "WAITING_EVIDENCE", detail=reason))
                continue
            if gated_by_trigger and not _trigger_satisfied(decision.trigger, quote.price):
                reason = f"trigger {decision.trigger.trigger_type.value} not yet satisfied at price {quote.price}"
                engine.record_gil_decision_watch(decision_id, reason)
                results.append(GilIngestionResult(decision_id, intent_id, "WAITING_EVIDENCE", detail=reason))
                continue
            price = quote.price

        resolved_quantity: Decimal | None = None
        sizing_note: str | None = None
        if decision.sizing is not None:
            resolved_quantity, sizing_note = _resolve_quantity(decision, price)
            if resolved_quantity is None:
                engine.record_gil_decision_watch(decision_id, sizing_note)
                results.append(GilIngestionResult(decision_id, intent_id, "WAITING_EVIDENCE", detail=sizing_note))
                continue

        try:
            status = ingest_gil_decision(engine, decision, resolved_quantity=resolved_quantity, sizing_note=sizing_note)
            engine.mark_gil_decision_processed(decision_id, outcome=status.value, outcome_reason=None, intent_id=intent_id)
            results.append(GilIngestionResult(decision_id, intent_id, status.value))
        except Experiment1Error as exc:
            engine.mark_gil_decision_processed(
                decision_id, outcome="BLOCKED", outcome_reason=str(exc), intent_id=intent_id
            )
            results.append(GilIngestionResult(decision_id, intent_id, "BLOCKED", detail=str(exc)))
    return tuple(results)
