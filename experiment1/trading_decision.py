from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import (
    AccountKind,
    DecisionAction,
    ExecutionTrigger,
    IntentStatus,
    OrderIntent,
    SizingIntent,
    SizingMode,
    TriggerType,
)

TRADING_ENVELOPE_MARKER = "TRADING DECISION ENVELOPE v1"
TRADING_ACCOUNTS = (AccountKind.SPOT, AccountKind.FUTURES)


def _nonblank(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-blank")


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class TradingDecision:
    """
    Strategy Lab -> Active Trading contract for Experiment 1.

    This is intentionally separate from GilDecision. It can target only
    the two Active Trading ledgers and never carries a GIL reference-close
    shortcut: Spot/Futures execution must continue through the existing
    Experiment1 paper lifecycle using fresh market evidence.

    The decision owns direction, symbol, sizing/risk inputs and optional
    structured trigger. MarketHunter owns policy validation and execution.
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
    trigger: ExecutionTrigger | None = None
    sizing: SizingIntent | None = None

    def __post_init__(self) -> None:
        _nonblank(self.decision_id, "decision_id")
        _nonblank(self.symbol, "symbol")
        _nonblank(self.thesis, "thesis")
        _aware(self.decided_at, "decided_at")

        if self.account not in TRADING_ACCOUNTS:
            raise ValueError("TradingDecision account must be SPOT or FUTURES")

        if self.account is AccountKind.SPOT:
            if self.action not in (
                DecisionAction.BUY,
                DecisionAction.SELL,
                DecisionAction.WAIT,
                DecisionAction.HOLD,
            ):
                raise ValueError("SPOT only allows BUY/SELL/WAIT/HOLD")
            if self.leverage != Decimal("1"):
                raise ValueError("SPOT leverage must be 1x")
        else:
            if self.action not in (
                DecisionAction.LONG,
                DecisionAction.SHORT,
                DecisionAction.WAIT,
                DecisionAction.HOLD,
            ):
                raise ValueError("FUTURES only allows LONG/SHORT/WAIT/HOLD")
            if self.leverage > Decimal("3"):
                raise ValueError("FUTURES leverage exceeds conservative 3x cap")

        if self.leverage <= 0:
            raise ValueError("leverage must be positive")

        if (self.quantity is None) == (self.sizing is None):
            raise ValueError("exactly one of quantity or sizing must be provided")

        if self.quantity is not None:
            if self.action in (DecisionAction.WAIT, DecisionAction.HOLD):
                if self.quantity != 0:
                    raise ValueError("WAIT/HOLD must use zero quantity")
            elif self.quantity <= 0:
                raise ValueError("trade decisions require positive quantity")

        if self.sizing is not None:
            if self.action in (DecisionAction.WAIT, DecisionAction.HOLD):
                raise ValueError("WAIT/HOLD cannot carry sizing")
            if self.sizing.mode is SizingMode.RISK_BUDGET_FROM_STOP and self.stop_loss is None:
                raise ValueError("RISK_BUDGET_FROM_STOP sizing requires stop_loss")


def intent_id_for(decision_id: str) -> str:
    _nonblank(decision_id, "decision_id")
    return f"trading-decision:{decision_id}"


def decision_id_from(intent_id: str) -> str | None:
    prefix = "trading-decision:"
    return intent_id[len(prefix):] if intent_id.startswith(prefix) else None


def to_order_intent(
    decision: TradingDecision,
    *,
    resolved_quantity: Decimal | None = None,
    sizing_note: str | None = None,
) -> OrderIntent:
    quantity = decision.quantity if resolved_quantity is None else resolved_quantity
    if quantity is None:
        raise ValueError("structured sizing must be resolved before OrderIntent mapping")
    reason = f"Trading decision {decision.decision_id}: {decision.thesis}"
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


def ingest_trading_decision(
    engine: Experiment1Engine,
    decision: TradingDecision,
    *,
    resolved_quantity: Decimal | None = None,
    sizing_note: str | None = None,
) -> IntentStatus:
    """
    Submit through the existing Experiment1 policy gate only.

    No fill is performed here. Fresh-evidence execution, SL/TP lifecycle,
    MTM and statistics remain owned by the existing Experiment1 runtime.
    """
    if resolved_quantity is None and decision.quantity is None:
        raise ValueError("structured sizing must be resolved from fresh market evidence before ingestion")
    return engine.submit_intent(
        to_order_intent(
            decision,
            resolved_quantity=resolved_quantity,
            sizing_note=sizing_note,
        )
    )


def decision_to_json(decision: TradingDecision) -> str:
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
            "trigger": None if decision.trigger is None else {
                "trigger_type": decision.trigger.trigger_type.value,
                "trigger_price": None if decision.trigger.trigger_price is None else str(decision.trigger.trigger_price),
                "trigger_price_low": None if decision.trigger.trigger_price_low is None else str(decision.trigger.trigger_price_low),
                "trigger_price_high": None if decision.trigger.trigger_price_high is None else str(decision.trigger.trigger_price_high),
                "note": decision.trigger.note,
            },
            "sizing": None if decision.sizing is None else {
                "mode": decision.sizing.mode.value,
                "exact_quantity": None if decision.sizing.exact_quantity is None else str(decision.sizing.exact_quantity),
                "max_notional": None if decision.sizing.max_notional is None else str(decision.sizing.max_notional),
                "risk_budget_amount": None if decision.sizing.risk_budget_amount is None else str(decision.sizing.risk_budget_amount),
            },
        },
        sort_keys=True,
    )


def decision_from_json(raw: str) -> TradingDecision:
    data = json.loads(raw)
    trigger_data = data.get("trigger")
    trigger = None
    if trigger_data is not None:
        trigger = ExecutionTrigger(
            trigger_type=TriggerType(trigger_data["trigger_type"]),
            trigger_price=None if trigger_data["trigger_price"] is None else Decimal(trigger_data["trigger_price"]),
            trigger_price_low=None if trigger_data["trigger_price_low"] is None else Decimal(trigger_data["trigger_price_low"]),
            trigger_price_high=None if trigger_data["trigger_price_high"] is None else Decimal(trigger_data["trigger_price_high"]),
            note=trigger_data["note"],
        )

    sizing_data = data.get("sizing")
    sizing = None
    if sizing_data is not None:
        sizing = SizingIntent(
            mode=SizingMode(sizing_data["mode"]),
            exact_quantity=None if sizing_data["exact_quantity"] is None else Decimal(sizing_data["exact_quantity"]),
            max_notional=None if sizing_data["max_notional"] is None else Decimal(sizing_data["max_notional"]),
            risk_budget_amount=None if sizing_data["risk_budget_amount"] is None else Decimal(sizing_data["risk_budget_amount"]),
        )

    return TradingDecision(
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
        trigger=trigger,
        sizing=sizing,
    )


class AsyncTradingQuoteSource(Protocol):
    async def quote_for(self, intent: OrderIntent): ...


@dataclass(frozen=True, slots=True)
class TradingIngestionResult:
    decision_id: str
    intent_id: str
    outcome: str
    detail: str | None = None


def _trigger_satisfied(trigger: ExecutionTrigger, price: Decimal) -> bool:
    if trigger.trigger_type is TriggerType.IMMEDIATE:
        return True
    if trigger.trigger_type is TriggerType.PRICE_AT_OR_ABOVE:
        return price >= trigger.trigger_price
    if trigger.trigger_type is TriggerType.PRICE_AT_OR_BELOW:
        return price <= trigger.trigger_price
    return trigger.trigger_price_low <= price <= trigger.trigger_price_high


def _resolve_sizing(
    decision: TradingDecision, price: Decimal | None
) -> tuple[Decimal | None, str | None]:
    sizing = decision.sizing
    if sizing is None:
        return decision.quantity, None
    if sizing.mode is SizingMode.EXACT_QUANTITY:
        return sizing.exact_quantity, f"sizing EXACT_QUANTITY={sizing.exact_quantity}"
    if price is None:
        return None, "fresh quote required to resolve trading sizing"
    if sizing.mode is SizingMode.MAX_NOTIONAL:
        quantity = sizing.max_notional / price
        return quantity, (
            f"sizing MAX_NOTIONAL={sizing.max_notional} @ price={price} "
            f"-> quantity={quantity}"
        )

    distance = abs(price - decision.stop_loss)
    if distance == 0:
        return None, (
            f"RISK_BUDGET_FROM_STOP cannot resolve because price {price} "
            f"equals stop_loss {decision.stop_loss}"
        )
    quantity = sizing.risk_budget_amount / distance
    return quantity, (
        f"sizing RISK_BUDGET_FROM_STOP={sizing.risk_budget_amount} "
        f"@ price={price} stop_loss={decision.stop_loss} -> quantity={quantity}"
    )


def _observation_intent(decision: TradingDecision) -> OrderIntent:
    return OrderIntent(
        intent_id=f"trading-observe:{decision.decision_id}",
        created_at=datetime.now(timezone.utc),
        account=decision.account,
        action=DecisionAction.WAIT,
        symbol=decision.symbol,
        quantity=Decimal("0"),
        reason="Active Trading trigger/sizing observation only",
        leverage=Decimal("1"),
    )


async def drain_trading_decision_inbox(
    engine: Experiment1Engine,
    quote_source: AsyncTradingQuoteSource,
) -> tuple[TradingIngestionResult, ...]:
    """
    Convert durable Strategy Lab decisions into canonical Experiment1 intents.

    Fixed-quantity immediate decisions require no quote at drain time. A
    non-immediate trigger or market-dependent sizing requires fresh quote
    evidence. If evidence is absent or the trigger is not satisfied, the row
    remains PENDING_DRAIN and is retried on a later runtime cycle.

    This function never fills an intent. The existing run_market_cycle remains
    the only paper execution path, preserving one execution engine for GIL and
    Active Trading.
    """
    results: list[TradingIngestionResult] = []

    for decision_id, raw_payload in engine.pending_trading_decision_inbox():
        decision = decision_from_json(raw_payload)
        intent_id = intent_id_for(decision.decision_id)

        if decision.action in (DecisionAction.WAIT, DecisionAction.HOLD):
            try:
                status = ingest_trading_decision(engine, decision)
            except (Experiment1Error, ValueError) as exc:
                engine.mark_trading_decision_processed(
                    decision_id,
                    outcome="BLOCKED",
                    outcome_reason=str(exc),
                    intent_id=intent_id,
                )
                results.append(
                    TradingIngestionResult(
                        decision_id, intent_id, "BLOCKED", detail=str(exc)
                    )
                )
                continue

            engine.mark_trading_decision_processed(
                decision_id,
                outcome=status.value,
                outcome_reason=None,
                intent_id=intent_id,
            )
            results.append(
                TradingIngestionResult(decision_id, intent_id, status.value)
            )
            continue

        gated_by_trigger = (
            decision.trigger is not None
            and decision.trigger.trigger_type is not TriggerType.IMMEDIATE
        )
        gated_by_sizing = (
            decision.sizing is not None
            and decision.sizing.mode
            in (SizingMode.MAX_NOTIONAL, SizingMode.RISK_BUDGET_FROM_STOP)
        )
        needs_quote = gated_by_trigger or gated_by_sizing

        price: Decimal | None = None
        if needs_quote:
            try:
                quote = await quote_source.quote_for(_observation_intent(decision))
            except Exception as exc:
                reason = f"quote lookup failed for {decision.symbol}: {exc}"
                engine.record_trading_decision_watch(decision_id, reason)
                results.append(
                    TradingIngestionResult(
                        decision_id, intent_id, "WAITING_EVIDENCE", reason
                    )
                )
                continue

            if quote is None:
                reason = f"no fresh quote available for {decision.symbol}"
                engine.record_trading_decision_watch(decision_id, reason)
                results.append(
                    TradingIngestionResult(
                        decision_id, intent_id, "WAITING_EVIDENCE", reason
                    )
                )
                continue
            price = quote.price

            if gated_by_trigger and not _trigger_satisfied(
                decision.trigger, price
            ):
                reason = (
                    f"trigger {decision.trigger.trigger_type.value} "
                    f"not satisfied at price {price}"
                )
                engine.record_trading_decision_watch(decision_id, reason)
                results.append(
                    TradingIngestionResult(
                        decision_id, intent_id, "WAITING_EVIDENCE", reason
                    )
                )
                continue

        resolved_quantity, sizing_note = _resolve_sizing(decision, price)
        if resolved_quantity is None:
            reason = sizing_note or "unable to resolve trading quantity"
            engine.record_trading_decision_watch(decision_id, reason)
            results.append(
                TradingIngestionResult(
                    decision_id, intent_id, "WAITING_EVIDENCE", reason
                )
            )
            continue

        try:
            status = ingest_trading_decision(
                engine,
                decision,
                resolved_quantity=resolved_quantity,
                sizing_note=sizing_note,
            )
        except (Experiment1Error, ValueError) as exc:
            engine.mark_trading_decision_processed(
                decision_id,
                outcome="BLOCKED",
                outcome_reason=str(exc),
                intent_id=intent_id,
            )
            results.append(
                TradingIngestionResult(
                    decision_id, intent_id, "BLOCKED", detail=str(exc)
                )
            )
            continue

        engine.mark_trading_decision_processed(
            decision_id,
            outcome=status.value,
            outcome_reason=None,
            intent_id=intent_id,
        )
        results.append(
            TradingIngestionResult(decision_id, intent_id, status.value)
        )

    return tuple(results)
