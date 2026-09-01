from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from experiment1.engine import Experiment1Engine
from experiment1.models import AccountKind, DecisionAction, OrderIntent
from experiment1.runtime import AsyncQuoteSource


@dataclass(frozen=True, slots=True)
class SymbolMarkResult:
    symbol: str
    outcome: str  # "FRESH_EVIDENCE" | "WAITING_EVIDENCE"
    price: Decimal | None = None
    source: str | None = None
    source_reference: str | None = None
    detail: str | None = None


class MtmCompleteness(str, Enum):
    """
    The account/cycle freshness-completeness contract: whether this
    cycle's equity/unrealized_pnl are backed by a fresh evidence-based
    mark for EVERY currently open symbol, or whether at least one
    symbol fell back to its own cost basis because its evidence was
    missing, stale, or unsupported this cycle.

    FULLY_FRESH_EVIDENCE: every open symbol had a fresh, valid quote
    this cycle - equity/unrealized_pnl are a complete, fully
    evidence-backed MTM snapshot. An account with zero open positions
    is trivially FULLY_FRESH_EVIDENCE - there is no missing evidence to
    have.

    PARTIAL_EVIDENCE_FALLBACK: at least one open symbol used its cost
    basis instead of a fresh mark (see SymbolMarkResult.outcome ==
    "WAITING_EVIDENCE" for which one). The cost-basis fallback is only
    a non-fabrication safety calculation - real, recorded, never a
    synthetic price - it must never be read as a complete or
    readiness-grade MTM state. Any downstream consumer (audit,
    statistics, a future readiness verdict) MUST check this field
    before treating equity/unrealized_pnl as fully fresh-evidence-
    backed.
    """

    FULLY_FRESH_EVIDENCE = "FULLY_FRESH_EVIDENCE"
    PARTIAL_EVIDENCE_FALLBACK = "PARTIAL_EVIDENCE_FALLBACK"


@dataclass(frozen=True, slots=True)
class MtmCycleResult:
    account: AccountKind
    symbol_results: tuple[SymbolMarkResult, ...]
    equity: Decimal
    unrealized_pnl: Decimal
    completeness: MtmCompleteness


def _observation_intent(account: AccountKind, symbol: str, now: datetime) -> OrderIntent:
    """
    A WAIT/zero-quantity carrier object that exists only to satisfy the
    AsyncQuoteSource.quote_for(intent) contract (it reads intent.symbol
    and intent.account only - see BinanceExperiment1QuoteSource). This
    is never submitted to the engine and never represents a trade
    decision - run_mtm_cycle is monitoring-only.
    """
    return OrderIntent(
        intent_id=f"mtm-observe:{account.value}:{symbol}",
        created_at=now,
        account=account,
        action=DecisionAction.WAIT,
        symbol=symbol,
        quantity=Decimal("0"),
        reason="continuous MTM repricing - observation only, never submitted to the engine",
    )


async def run_mtm_cycle(
    engine: Experiment1Engine,
    quote_source: AsyncQuoteSource,
    account: AccountKind,
    *,
    now: datetime | None = None,
) -> MtmCycleResult:
    """
    Reprice every currently open position in `account` from fresh
    evidence, updating NAV/equity/unrealized P&L/drawdown. Strictly
    monitoring: never submits an intent, never creates a fill, never
    makes a BUY/SELL/LONG/SHORT decision - the only engine write is
    Experiment1Engine.reprice_open_positions' own equity snapshot.

    A symbol whose fresh quote is unavailable, stale (see
    FreshnessGuardedQuoteSource), or unsupported (see
    MultiAssetQuoteSource / UnavailableQuoteProvider for the
    non-crypto BLOCKED-EVIDENCE path) keeps its existing cost-basis
    valuation - reprice_open_positions' own non-fabrication guarantee -
    and is reported here as WAITING_EVIDENCE per symbol, never silently
    hidden inside one account-wide result. The returned `completeness`
    makes this unmistakable at the account/cycle level too: it is
    PARTIAL_EVIDENCE_FALLBACK whenever any open symbol used cost-basis
    fallback this cycle, never silently reported as a complete
    fresh-evidence MTM state. Independent ledgers stay independent -
    each call is scoped to exactly one `account`, so one account's
    partial evidence never taints another's completeness.

    Restart-safe and idempotent by construction: all state this cycle
    reads and writes lives in the engine's own database, never in a
    caller-held object, so calling this repeatedly - including across a
    fresh Experiment1Engine instance over the same db file - reproduces
    the same result for the same underlying market state.
    """
    moment = now or datetime.now(timezone.utc)
    positions = engine.positions(account)

    symbol_results: list[SymbolMarkResult] = []
    marks: dict[str, Decimal] = {}
    for position in positions:
        intent = _observation_intent(account, position.symbol, moment)
        try:
            quote = await quote_source.quote_for(intent)
        except Exception as exc:
            symbol_results.append(SymbolMarkResult(position.symbol, "WAITING_EVIDENCE", detail=str(exc)))
            continue
        if quote is None:
            symbol_results.append(SymbolMarkResult(position.symbol, "WAITING_EVIDENCE"))
            continue
        marks[position.symbol] = quote.price
        symbol_results.append(
            SymbolMarkResult(
                position.symbol,
                "FRESH_EVIDENCE",
                price=quote.price,
                source=quote.source,
                source_reference=quote.source_reference,
            )
        )

    state = engine.reprice_open_positions(account, marks)

    # Same formula reprice_open_positions() applies internally per
    # position (qty * (mark - avg), cost-basis fallback for any symbol
    # missing from marks) - recomputed here from the public positions()
    # snapshot rather than reaching into engine internals a second time.
    unrealized_pnl = sum(
        (position.quantity * (marks.get(position.symbol, position.average_price) - position.average_price) for position in positions),
        start=Decimal("0"),
    )

    completeness = (
        MtmCompleteness.PARTIAL_EVIDENCE_FALLBACK
        if any(result.outcome == "WAITING_EVIDENCE" for result in symbol_results)
        else MtmCompleteness.FULLY_FRESH_EVIDENCE
    )

    return MtmCycleResult(account, tuple(symbol_results), state.last_equity, unrealized_pnl, completeness)
