from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from experiment1.engine import Experiment1Engine, Experiment1Error, NO_LEVERAGE_ACCOUNTS
from experiment1.models import DecisionAction, FillRecord, OrderIntent
from experiment1.runtime import AsyncQuoteSource


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    entry_intent_id: str
    outcome: str
    detail: str | None = None
    exit_fill: FillRecord | None = None


def _trigger_reason(intent: OrderIntent, price: Decimal) -> str | None:
    if intent.action in (DecisionAction.BUY, DecisionAction.LONG):
        if intent.stop_loss is not None and price <= intent.stop_loss:
            return "STOP_LOSS"
        if intent.take_profit is not None and price >= intent.take_profit:
            return "TAKE_PROFIT"
    elif intent.action is DecisionAction.SHORT:
        if intent.stop_loss is not None and price >= intent.stop_loss:
            return "STOP_LOSS"
        if intent.take_profit is not None and price <= intent.take_profit:
            return "TAKE_PROFIT"
    return None


def _exit_action(intent: OrderIntent) -> DecisionAction:
    if intent.account in NO_LEVERAGE_ACCOUNTS:
        return DecisionAction.SELL
    if intent.action is DecisionAction.LONG:
        return DecisionAction.SHORT
    if intent.action is DecisionAction.SHORT:
        return DecisionAction.LONG
    raise Experiment1Error("entry intent has no protective exit action")


async def run_protective_exit_cycle(
    engine: Experiment1Engine,
    quote_source: AsyncQuoteSource,
    entry_intent_ids: tuple[str, ...],
) -> tuple[LifecycleResult, ...]:
    """Evaluate stop-loss/take-profit instructions against fresh public evidence.

    Protective exits are deterministic contingent instructions derived from the
    original entry intent. They never invent a price or bypass the paper engine.
    """

    results: list[LifecycleResult] = []
    for entry_intent_id in entry_intent_ids:
        try:
            entry = engine.get_intent(entry_intent_id)
            if entry.action not in (DecisionAction.BUY, DecisionAction.LONG, DecisionAction.SHORT):
                results.append(LifecycleResult(entry_intent_id, "NOT_ENTRY"))
                continue
            if entry.stop_loss is None and entry.take_profit is None:
                results.append(LifecycleResult(entry_intent_id, "NO_PROTECTIVE_RULE"))
                continue

            positions = {p.symbol: p for p in engine.positions(entry.account)}
            position = positions.get(entry.symbol)
            if position is None or position.quantity == 0:
                results.append(LifecycleResult(entry_intent_id, "ALREADY_CLOSED"))
                continue

            quote = await quote_source.quote_for(entry)
            if quote is None:
                results.append(LifecycleResult(entry_intent_id, "WAITING_EVIDENCE"))
                continue

            reason = _trigger_reason(entry, quote.price)
            if reason is None:
                results.append(LifecycleResult(entry_intent_id, "ACTIVE"))
                continue

            quantity = abs(position.quantity)
            exit_intent = OrderIntent(
                intent_id=f"{entry.intent_id}:protective:{reason}",
                created_at=entry.created_at,
                account=entry.account,
                action=_exit_action(entry),
                symbol=entry.symbol,
                quantity=quantity,
                reason=f"Protective {reason} from {entry.intent_id}",
                leverage=position.leverage,
            )
            engine.submit_intent(exit_intent)
            fill = engine.execute_pending(exit_intent.intent_id, quote)
            results.append(LifecycleResult(entry_intent_id, reason, exit_fill=fill))
        except Experiment1Error as exc:
            results.append(LifecycleResult(entry_intent_id, "SKIPPED", detail=str(exc)))
        except Exception as exc:
            results.append(LifecycleResult(entry_intent_id, "SOURCE_ERROR", detail=str(exc)))
    return tuple(results)
