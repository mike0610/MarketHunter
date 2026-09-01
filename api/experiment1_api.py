from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import AccountKind, DecisionAction, MarketQuote, OrderIntent


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
