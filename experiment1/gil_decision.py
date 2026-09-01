from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import GilDecision, IntentStatus, OrderIntent


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
