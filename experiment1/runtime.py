from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import FillRecord, MarketQuote, OrderIntent


class AsyncQuoteSource(Protocol):
    async def quote_for(self, intent: OrderIntent) -> MarketQuote | None: ...


@dataclass(frozen=True, slots=True)
class CycleResult:
    intent_id: str
    outcome: str
    detail: str | None = None
    fill: FillRecord | None = None


async def run_market_cycle(
    engine: Experiment1Engine,
    quote_source: AsyncQuoteSource,
) -> tuple[CycleResult, ...]:
    """Process one bounded paper-market cycle for every pending intent."""

    results: list[CycleResult] = []
    for intent_id in engine.pending_intent_ids():
        try:
            intent = engine.get_intent(intent_id)
            quote = await quote_source.quote_for(intent)
            if quote is None:
                results.append(CycleResult(intent_id, "WAITING_EVIDENCE"))
                continue
            fill = engine.execute_pending(intent_id, quote)
            results.append(CycleResult(intent_id, "PAPER_FILLED", fill=fill))
        except Experiment1Error as exc:
            results.append(CycleResult(intent_id, "SKIPPED", detail=str(exc)))
        except Exception as exc:
            results.append(CycleResult(intent_id, "SOURCE_ERROR", detail=str(exc)))
    return tuple(results)
