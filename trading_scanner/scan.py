"""
MarketHunter

trading_scanner/scan.py

Module:
The bounded scan-cycle orchestration: universe -> liquidity gate ->
setup classification -> persistent queue. This is the ONLY place this
package's pieces are wired together, and it is the load-bearing proof
of the dispatch's hard boundary:

    Scanner MUST NOT emit BUY/SELL/LONG/SHORT.
    Scanner MUST NOT create OrderIntent or bypass GIL Decision ->
    MarketHunter paper execution boundary.

This module - and this entire package - imports nothing from
experiment1.engine, experiment1.gil_decision, or any other module that
can submit an intent or execute a fill. It only ever calls
TradingScannerStore.record_candidate, which writes to this package's
own, entirely separate trading_scanner_candidates table. See
tests/test_trading_scanner_boundary.py for a structural proof (the
compiled bytecode of this whole package is scanned for any reference
to a forbidden name), not just a behavioral one.

This bounded slice wires exactly one setup family
(MOMENTUM_RELATIVE_STRENGTH) - ABNORMAL_VOLUME_CATALYST and
BREAKOUT_OR_PULLBACK_IN_TREND are deliberately deferred (see
trading_scanner/setups.py's own docstring). A read API and a
scheduler/systemd runtime hook are also deliberately deferred to a
follow-up slice, per explicit direct guidance this cycle to keep
changes minimal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from experiment1.models import SessionState
from trading_scanner.gates import evaluate_liquidity_gate
from trading_scanner.models import (
    IbkrContract,
    LiquidityContext,
    QueueState,
    SetupFamily,
    TradingCandidate,
    VolatilityContext,
)
from trading_scanner.setups import classify_momentum_relative_strength
from trading_scanner.store import TradingScannerStore
from trading_scanner.universe import AsyncIbkrUniverseSource


@dataclass(frozen=True, slots=True)
class ScanCycleResult:
    scan_cycle_id: str
    contracts_seen: int
    candidates_recorded: tuple[TradingCandidate, ...]


def _dedupe_key(conid: int, setup_family: SetupFamily, scan_cycle_id: str) -> str:
    return f"{conid}:{setup_family.value}:{scan_cycle_id}"


def _realized_range_pct(market_data) -> Decimal:
    close = market_data.closes[-1]
    high = max(market_data.highs[-20:]) if len(market_data.highs) >= 20 else max(market_data.highs)
    low = min(market_data.lows[-20:]) if len(market_data.lows) >= 20 else min(market_data.lows)
    if close == 0:
        return Decimal("0")
    return ((high - low) / close) * Decimal("100")


async def run_scan_cycle(
    universe_source: AsyncIbkrUniverseSource,
    store: TradingScannerStore,
    *,
    scan_cycle_id: str | None = None,
    session_state: SessionState = SessionState.REGULAR,
    now: datetime | None = None,
) -> ScanCycleResult:
    """
    One bounded pass: resolve the IBKR universe, gate each contract for
    liquidity/executability, classify eligible contracts against the
    one wired setup family (MOMENTUM_RELATIVE_STRENGTH), and record
    every outcome - match or not, eligible or not, data-available or
    not - to the persistent queue. Never raises on a per-contract
    failure; a contract with unavailable market data is recorded
    DATA_FAIL, never silently skipped.

    session_state is caller-supplied (the real market clock, not
    derived here) - this function makes no claim about what time it
    actually is, matching this package's own "no fabricated evidence"
    discipline throughout.
    """
    moment = now or datetime.now(timezone.utc)
    cycle_id = scan_cycle_id or moment.isoformat()

    contracts = await universe_source.resolve_universe()
    recorded: list[TradingCandidate] = []

    for contract in contracts:
        liquidity = await universe_source.liquidity_context_for(contract)
        if liquidity is None:
            recorded.append(
                _record_data_fail(store, contract, cycle_id, moment, "no liquidity context available for this contract")
            )
            continue

        gate = evaluate_liquidity_gate(liquidity, session_state)
        if not gate.eligible:
            recorded.append(
                _record_ineligible(store, contract, liquidity, cycle_id, moment, gate.reasons)
            )
            continue

        market_data = await universe_source.market_data_for(contract)
        if market_data is None:
            recorded.append(
                _record_data_fail(store, contract, cycle_id, moment, "no market data available for this contract")
            )
            continue

        classification = classify_momentum_relative_strength(market_data)
        if classification is None:
            recorded.append(
                _record_data_fail(
                    store, contract, cycle_id, moment, "insufficient history to compute the momentum rule"
                )
            )
            continue

        queue_state = QueueState.CANDIDATE if classification.matched else QueueState.WATCH
        candidate = TradingCandidate(
            conid=contract.conid,
            symbol=contract.symbol,
            sec_type=contract.sec_type,
            exchange=contract.exchange,
            currency=contract.currency,
            setup_family=SetupFamily.MOMENTUM_RELATIVE_STRENGTH,
            reason_stack=classification.reason_stack,
            liquidity=liquidity,
            volatility=VolatilityContext(realized_range_pct=_realized_range_pct(market_data)),
            evidence_status="OK",
            eligible=True,
            discovered_at=moment,
            scan_cycle_id=cycle_id,
            dedupe_key=_dedupe_key(contract.conid, SetupFamily.MOMENTUM_RELATIVE_STRENGTH, cycle_id),
            queue_state=queue_state,
            invalidation_reference=classification.invalidation_reference,
        )
        recorded.append(store.record_candidate(candidate))

    return ScanCycleResult(scan_cycle_id=cycle_id, contracts_seen=len(contracts), candidates_recorded=tuple(recorded))


def _record_data_fail(store: TradingScannerStore, contract: IbkrContract, cycle_id: str, moment: datetime, reason: str) -> TradingCandidate:
    candidate = TradingCandidate(
        conid=contract.conid,
        symbol=contract.symbol,
        sec_type=contract.sec_type,
        exchange=contract.exchange,
        currency=contract.currency,
        setup_family=SetupFamily.MOMENTUM_RELATIVE_STRENGTH,
        reason_stack=(reason,),
        liquidity=LiquidityContext(
            average_daily_volume=Decimal("0"), average_daily_dollar_volume=Decimal("0"), last_price=Decimal("0.01")
        ),
        volatility=VolatilityContext(realized_range_pct=Decimal("0")),
        evidence_status="MISSING",
        eligible=False,
        discovered_at=moment,
        scan_cycle_id=cycle_id,
        dedupe_key=_dedupe_key(contract.conid, SetupFamily.MOMENTUM_RELATIVE_STRENGTH, cycle_id),
        queue_state=QueueState.DATA_FAIL,
        reject_reason=reason,
    )
    return store.record_candidate(candidate)


def _record_ineligible(
    store: TradingScannerStore,
    contract: IbkrContract,
    liquidity: LiquidityContext,
    cycle_id: str,
    moment: datetime,
    reasons: tuple[str, ...],
) -> TradingCandidate:
    candidate = TradingCandidate(
        conid=contract.conid,
        symbol=contract.symbol,
        sec_type=contract.sec_type,
        exchange=contract.exchange,
        currency=contract.currency,
        setup_family=SetupFamily.MOMENTUM_RELATIVE_STRENGTH,
        reason_stack=reasons,
        liquidity=liquidity,
        volatility=VolatilityContext(realized_range_pct=Decimal("0")),
        evidence_status="OK",
        eligible=False,
        discovered_at=moment,
        scan_cycle_id=cycle_id,
        dedupe_key=_dedupe_key(contract.conid, SetupFamily.MOMENTUM_RELATIVE_STRENGTH, cycle_id),
        queue_state=QueueState.INELIGIBLE,
        reject_reason="; ".join(reasons),
    )
    return store.record_candidate(candidate)
