from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.gil_decision import decision_to_json
from experiment1.models import (
    AccountKind,
    DecisionAction,
    ExecutionTrigger,
    GilDecision,
    GilInboxRecord,
    MarketQuote,
    OrderIntent,
    SizingIntent,
    SizingMode,
    TriggerType,
)


router = APIRouter(prefix="/experiment1", tags=["experiment1"])


def _engine() -> Experiment1Engine:
    path = Path(os.getenv("EXPERIMENT1_DB_PATH", "data/experiment1.db"))
    return Experiment1Engine(path)


class IntentRequest(BaseModel):
    intent_id: str = Field(min_length=1)
    created_at: datetime
    account: AccountKind
    action: DecisionAction
    symbol: str = Field(min_length=1)
    quantity: Decimal = Field(ge=0)
    reason: str = Field(min_length=1)
    leverage: Decimal = Field(default=Decimal("1"), gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)


class ExecutionTriggerRequest(BaseModel):
    """Mirrors experiment1.models.ExecutionTrigger - a structured, objectively-evaluable execution gate."""

    trigger_type: TriggerType
    trigger_price: Decimal | None = Field(default=None, gt=0)
    trigger_price_low: Decimal | None = Field(default=None, gt=0)
    trigger_price_high: Decimal | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, min_length=1)


class SizingIntentRequest(BaseModel):
    """Mirrors experiment1.models.SizingIntent - GIL's canonical sizing intent."""

    mode: SizingMode
    exact_quantity: Decimal | None = Field(default=None, gt=0)
    max_notional: Decimal | None = Field(default=None, gt=0)
    risk_budget_amount: Decimal | None = Field(default=None, gt=0)


class GilDecisionRequest(BaseModel):
    """
    The canonical GIL Decision Inbox contract: POST /experiment1/gil-decisions.
    Accepts exactly the existing GilDecision semantics from PR #77 -
    no trade field is invented here, and action is restricted to the
    already-decided DecisionAction enum, so free-text research states
    (CANDIDATE, WATCH, ...) are rejected by FastAPI's own schema
    validation before ever reaching domain logic, never coerced.

    Exactly one of `quantity` (a fixed amount GIL already decided) or
    `sizing` (resolved from fresh evidence - see SizingIntentRequest)
    must be provided. `trigger` is optional - omitted or IMMEDIATE means
    submit as soon as risk-validated, matching the original behavior.
    """

    decision_id: str = Field(min_length=1)
    decided_at: datetime
    account: AccountKind
    action: DecisionAction
    symbol: str = Field(min_length=1)
    thesis: str = Field(min_length=1)
    quantity: Decimal | None = Field(default=None, ge=0)
    leverage: Decimal = Field(default=Decimal("1"), gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    execution_condition: str | None = Field(default=None, min_length=1)
    trigger: ExecutionTriggerRequest | None = None
    sizing: SizingIntentRequest | None = None


class QuoteRequest(BaseModel):
    symbol: str = Field(min_length=1)
    price: Decimal = Field(gt=0)
    observed_at: datetime
    source: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    fee_bps: Decimal = Field(ge=0)
    slippage_bps: Decimal = Field(ge=0)


@router.post("/intents")
def submit_intent(payload: IntentRequest):
    try:
        status = _engine().submit_intent(OrderIntent(**payload.model_dump()))
    except (Experiment1Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"intent_id": payload.intent_id, "status": status.value, "simulation_only": True}


@router.post("/intents/{intent_id}/paper-fill")
def paper_fill(intent_id: str, payload: QuoteRequest):
    try:
        fill = _engine().execute_pending(intent_id, MarketQuote(**payload.model_dump()))
    except (Experiment1Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "intent_id": fill.intent_id,
        "account": fill.account.value,
        "action": fill.action.value,
        "symbol": fill.symbol,
        "quantity": str(fill.quantity),
        "reference_price": str(fill.reference_price),
        "fill_price": str(fill.fill_price),
        "fee": str(fill.fee),
        "leverage": str(fill.leverage),
        "observed_at": fill.observed_at.isoformat(),
        "source": fill.source,
        "source_reference": fill.source_reference,
        "simulation_only": True,
    }


def _gil_inbox_response(record: GilInboxRecord) -> dict:
    return {
        "decision_id": record.decision_id,
        "received_at": record.received_at.isoformat(),
        "status": record.status.value,
        "outcome": record.outcome,
        "outcome_reason": record.outcome_reason,
        "intent_id": record.intent_id,
        "processed_at": None if record.processed_at is None else record.processed_at.isoformat(),
        "simulation_only": True,
    }


@router.post("/gil-decisions")
def submit_gil_decision(payload: GilDecisionRequest):
    """
    Durable receipt only - see experiment1.gil_decision.drain_gil_decision_inbox
    for the actual GilDecision -> OrderIntent -> risk-validation
    processing, which the runtime scheduler runs automatically each
    cycle. This endpoint never calls submit_intent/execute_pending
    itself - there is no parallel execution path.
    """
    engine = _engine()
    try:
        decision = GilDecision(
            decision_id=payload.decision_id,
            decided_at=payload.decided_at,
            account=payload.account,
            action=payload.action,
            symbol=payload.symbol,
            thesis=payload.thesis,
            quantity=payload.quantity,
            leverage=payload.leverage,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
            execution_condition=payload.execution_condition,
            trigger=None if payload.trigger is None else ExecutionTrigger(**payload.trigger.model_dump()),
            sizing=None if payload.sizing is None else SizingIntent(**payload.sizing.model_dump()),
        )
    except ValueError as exc:
        try:
            engine.record_malformed_gil_decision(payload.decision_id, payload.model_dump_json(), str(exc))
        except Experiment1Error as collision:
            raise HTTPException(status_code=409, detail=str(collision)) from collision
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        record = engine.receive_gil_decision(decision.decision_id, decision_to_json(decision))
    except Experiment1Error as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _gil_inbox_response(record)


@router.get("/gil-decisions/{decision_id}")
def gil_decision_status(decision_id: str):
    record = _engine().gil_decision_inbox_status(decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown decision_id")
    return _gil_inbox_response(record)


@router.get("/state")
def state():
    engine = _engine()
    accounts = []
    for account in AccountKind:
        try:
            snapshot = engine.account_state(account)
        except Experiment1Error:
            # AccountKind.INVESTMENTS (legacy) is never (re)created for a
            # fresh deployment - only report accounts that actually exist,
            # never fabricate a zero-state for one that was never
            # initialized.
            continue
        accounts.append(
            {
                "account": account.value,
                "starting_cash": str(snapshot.starting_cash),
                "cash": str(snapshot.cash),
                "realized_pnl": str(snapshot.realized_pnl),
                "fees_paid": str(snapshot.fees_paid),
                "last_equity": str(snapshot.last_equity),
                "peak_equity": str(snapshot.peak_equity),
                "max_drawdown": str(snapshot.max_drawdown),
                "used_margin": str(snapshot.used_margin),
                "available_cash": str(snapshot.available_cash),
                "positions": [
                    {
                        "symbol": position.symbol,
                        "quantity": str(position.quantity),
                        "average_price": str(position.average_price),
                        "leverage": str(position.leverage),
                        "margin": str(position.margin),
                        "notional": str(position.notional),
                    }
                    for position in engine.positions(account)
                ],
            }
        )
    return {"experiment": "GIL Sandbox Experiment 1", "simulation_only": True, "accounts": accounts}
