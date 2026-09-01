from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import FillRecord, MarketQuote


QuoteProvider = Callable[[str], MarketQuote | None]


@dataclass(frozen=True, slots=True)
class WatchResult:
    intent_id: str
    outcome: str
    detail: str | None = None
    fill: FillRecord | None = None


class Experiment1Watcher:
    """One deterministic watcher cycle for pending Experiment 1 intents.

    The watcher never invents quotes or execution costs. A caller must provide
    governed market evidence through ``quote_provider``. Missing or invalid
    evidence leaves the intent pending for a later cycle.
    """

    def __init__(self, engine: Experiment1Engine, quote_provider: QuoteProvider) -> None:
        self.engine = engine
        self.quote_provider = quote_provider

    def run_once(self, intent_ids: Iterable[str] | None = None) -> tuple[WatchResult, ...]:
        pending = tuple(intent_ids) if intent_ids is not None else self.engine.pending_intent_ids()
        results: list[WatchResult] = []
        for intent_id in pending:
            try:
                intent = self.engine.get_intent(intent_id)
                quote = self.quote_provider(intent.symbol)
                if quote is None:
                    results.append(WatchResult(intent_id, "WAITING_EVIDENCE"))
                    continue
                fill = self.engine.execute_pending(intent_id, quote)
                results.append(WatchResult(intent_id, "PAPER_FILLED", fill=fill))
            except Experiment1Error as exc:
                results.append(WatchResult(intent_id, "SKIPPED", detail=str(exc)))
        return tuple(results)
