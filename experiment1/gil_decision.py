from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import AccountKind, DecisionAction, GilDecision, IntentStatus, OrderIntent


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


def to_order_intent(decision: GilDecision) -> OrderIntent:
    """
    Deterministic, lossless mapping from a GIL Decision to the existing
    canonical OrderIntent. Every GIL-owned field - action, symbol,
    quantity, leverage, stop_loss, take_profit - is copied verbatim,
    never defaulted or reinterpreted by MarketHunter. `reason` carries
    GIL's own thesis text plus the decision_id for human-readable
    audit; intent_id carries the same provenance structurally (see
    intent_id_for/decision_id_from).
    """
    return OrderIntent(
        intent_id=intent_id_for(decision.decision_id),
        created_at=decision.decided_at,
        account=decision.account,
        action=decision.action,
        symbol=decision.symbol,
        quantity=decision.quantity,
        reason=f"GIL decision {decision.decision_id}: {decision.thesis}",
        leverage=decision.leverage,
        stop_loss=decision.stop_loss,
        take_profit=decision.take_profit,
    )


def ingest_gil_decision(engine: Experiment1Engine, decision: GilDecision) -> IntentStatus:
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
    return engine.submit_intent(to_order_intent(decision))


@dataclass(frozen=True, slots=True)
class GilIngestionResult:
    decision_id: str
    intent_id: str
    outcome: str  # IntentStatus value, or "BLOCKED" on a newly-rejected decision
    detail: str | None = None


def run_gil_ingestion_cycle(
    engine: Experiment1Engine, decisions: Iterable[GilDecision]
) -> tuple[GilIngestionResult, ...]:
    """
    Ingest a batch of GIL decisions, catching a per-decision policy
    rejection rather than aborting the whole batch - the same
    catch-and-report shape already used by run_market_cycle and
    run_protective_exit_cycle for their own per-item iteration.
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
            "quantity": str(decision.quantity),
            "leverage": str(decision.leverage),
            "stop_loss": None if decision.stop_loss is None else str(decision.stop_loss),
            "take_profit": None if decision.take_profit is None else str(decision.take_profit),
            "execution_condition": decision.execution_condition,
        },
        sort_keys=True,
    )


def decision_from_json(raw: str) -> GilDecision:
    """Inverse of decision_to_json."""
    data = json.loads(raw)
    return GilDecision(
        decision_id=data["decision_id"],
        decided_at=datetime.fromisoformat(data["decided_at"]),
        account=AccountKind(data["account"]),
        action=DecisionAction(data["action"]),
        symbol=data["symbol"],
        thesis=data["thesis"],
        quantity=Decimal(data["quantity"]),
        leverage=Decimal(data["leverage"]),
        stop_loss=None if data["stop_loss"] is None else Decimal(data["stop_loss"]),
        take_profit=None if data["take_profit"] is None else Decimal(data["take_profit"]),
        execution_condition=data.get("execution_condition"),
    )


_NO_EVALUATOR_REASON = (
    "execution_condition is present but no evaluator exists in this environment that can "
    "objectively verify an arbitrary condition against market evidence - failing closed as "
    "WAITING_EVIDENCE rather than guessing"
)


def drain_gil_decision_inbox(engine: Experiment1Engine) -> tuple[GilIngestionResult, ...]:
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
    directly, with the condition itself preserved in the inbox row -
    never submitted to ingest_gil_decision. Every other decision goes
    through the exact same ingest_gil_decision path as a directly
    ingested one - same risk validation, same BLOCKED-persistence
    contract, same idempotency.

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

        try:
            status = ingest_gil_decision(engine, decision)
            engine.mark_gil_decision_processed(decision_id, outcome=status.value, outcome_reason=None, intent_id=intent_id)
            results.append(GilIngestionResult(decision_id, intent_id, status.value))
        except Experiment1Error as exc:
            engine.mark_gil_decision_processed(
                decision_id, outcome="BLOCKED", outcome_reason=str(exc), intent_id=intent_id
            )
            results.append(GilIngestionResult(decision_id, intent_id, "BLOCKED", detail=str(exc)))
    return tuple(results)
