"""
MarketHunter

trading_scanner/scan.py

Module:
The bounded scan-cycle orchestration: universe -> liquidity gate ->
setup classification (all 3 v1 families) -> persistent queue. This is
the ONLY place this package's pieces are wired together, and it is the
load-bearing proof of the dispatch's hard boundary:

    Scanner MUST NOT emit BUY/SELL/LONG/SHORT.
    Scanner MUST NOT create OrderIntent or bypass GIL Decision ->
    MarketHunter paper execution boundary.

This module - and this entire package - imports nothing from
experiment1.engine, experiment1.gil_decision, or any other module that
can submit an intent or execute a fill. It only ever calls
TradingScannerStore.record_candidate, which writes to this package's
own, entirely separate trading_scanner_candidates table. See
tests/test_trading_scanner_boundary.py for a structural proof (the
real AST of this whole package is scanned for any reference to a
forbidden name), not just a behavioral one.

Each eligible contract is evaluated against all three v1 setup
families independently - a contract can appear in the queue up to
three times per cycle (one row per family, each with its own
dedupe_key), matching "explicit strategy compatibility is evaluated
per family" rather than collapsing multiple setups into one opaque
row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from experiment1.models import SessionState
from trading_scanner.gates import DEFAULT_LIQUIDITY_THRESHOLDS, LiquidityThresholds, evaluate_liquidity_gate
from trading_scanner.models import (
    IbkrContract,
    LiquidityContext,
    QueueState,
    SetupFamily,
    TradingCandidate,
    VolatilityContext,
)
from trading_scanner.setups import (
    SetupClassification,
    classify_abnormal_volume_catalyst,
    classify_breakout_or_pullback_in_trend,
    classify_momentum_relative_strength,
)
from trading_scanner.store import TradingScannerStore
from trading_scanner.universe import AsyncIbkrUniverseSource, ContractMarketData


@dataclass(frozen=True, slots=True)
class ScanCycleResult:
    scan_cycle_id: str
    contracts_seen: int
    candidates_recorded: tuple[TradingCandidate, ...]


def _dedupe_key(conid: int, setup_family: SetupFamily, scan_cycle_id: str) -> str:
    return f"{conid}:{setup_family.value}:{scan_cycle_id}"


def _realized_range_pct(market_data: ContractMarketData) -> Decimal:
    close = market_data.closes[-1]
    high = max(market_data.highs[-20:]) if len(market_data.highs) >= 20 else max(market_data.highs)
    low = min(market_data.lows[-20:]) if len(market_data.lows) >= 20 else min(market_data.lows)
    if close == 0:
        return Decimal("0")
    return ((high - low) / close) * Decimal("100")


def _freshness_note(market_data: ContractMarketData, moment: datetime) -> str:
    age = moment - market_data.observed_at
    return f"history observed_at={market_data.observed_at.isoformat()} (age={age})"


async def run_scan_cycle(
    universe_source: AsyncIbkrUniverseSource,
    store: TradingScannerStore,
    *,
    scan_cycle_id: str | None = None,
    session_state: SessionState = SessionState.REGULAR,
    now: datetime | None = None,
    liquidity_thresholds: LiquidityThresholds = DEFAULT_LIQUIDITY_THRESHOLDS,
    benchmark_contract: IbkrContract | None = None,
) -> ScanCycleResult:
    """
    One bounded pass: resolve the IBKR universe, gate each contract for
    liquidity/executability/restriction, and - for every eligible
    contract - classify against all three v1 setup families
    independently, recording every outcome (match, watch, or
    data-fail) to the persistent queue. A gated-out (ineligible) or
    data-unavailable contract is recorded once, not once per family -
    there is nothing family-specific to say about a contract the gate
    or the data fetch already rejected outright.

    `benchmark_contract`, if given, is resolved once per cycle and
    passed to MOMENTUM_RELATIVE_STRENGTH's optional relative-strength
    leg for every symbol this cycle - never fetched per-symbol, and
    never required (see trading_scanner/setups.py).

    Never raises on a per-contract failure; a contract with
    unavailable market data is recorded DATA_FAIL, never silently
    skipped.
    """
    moment = now or datetime.now(timezone.utc)
    cycle_id = scan_cycle_id or moment.isoformat()

    contracts = await universe_source.resolve_universe()
    recorded: list[TradingCandidate] = []

    benchmark_data: ContractMarketData | None = None
    if benchmark_contract is not None:
        benchmark_data = await universe_source.market_data_for(benchmark_contract)

    for contract in contracts:
        liquidity = await universe_source.liquidity_context_for(contract)
        if liquidity is None:
            recorded.append(
                _record_data_fail(store, contract, cycle_id, moment, "no liquidity context available for this contract")
            )
            continue

        gate = evaluate_liquidity_gate(contract, liquidity, session_state, liquidity_thresholds)
        if not gate.eligible:
            recorded.append(_record_ineligible(store, contract, liquidity, cycle_id, moment, gate.reasons))
            continue

        market_data = await universe_source.market_data_for(contract)
        if market_data is None:
            recorded.append(
                _record_data_fail(store, contract, cycle_id, moment, "no market data available for this contract")
            )
            continue

        freshness_note = _freshness_note(market_data, moment)
        volatility = VolatilityContext(realized_range_pct=_realized_range_pct(market_data))

        momentum = classify_momentum_relative_strength(market_data, benchmark_data)
        recorded.append(
            _record_setup_outcome(
                store, contract, liquidity, volatility, cycle_id, moment, freshness_note,
                SetupFamily.MOMENTUM_RELATIVE_STRENGTH, momentum,
            )
        )

        catalyst = await universe_source.catalyst_for(contract)
        volume_catalyst = classify_abnormal_volume_catalyst(market_data, catalyst)
        recorded.append(
            _record_setup_outcome(
                store, contract, liquidity, volatility, cycle_id, moment, freshness_note,
                SetupFamily.ABNORMAL_VOLUME_CATALYST, volume_catalyst, catalyst=catalyst,
            )
        )

        breakout_pullback = classify_breakout_or_pullback_in_trend(market_data)
        recorded.append(
            _record_setup_outcome(
                store, contract, liquidity, volatility, cycle_id, moment, freshness_note,
                SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND, breakout_pullback,
            )
        )

    return ScanCycleResult(scan_cycle_id=cycle_id, contracts_seen=len(contracts), candidates_recorded=tuple(recorded))


def _record_setup_outcome(
    store: TradingScannerStore,
    contract: IbkrContract,
    liquidity: LiquidityContext,
    volatility: VolatilityContext,
    cycle_id: str,
    moment: datetime,
    freshness_note: str,
    setup_family: SetupFamily,
    classification: SetupClassification | None,
    *,
    catalyst=None,
) -> TradingCandidate:
    dedupe_key = _dedupe_key(contract.conid, setup_family, cycle_id)
    if classification is None:
        candidate = TradingCandidate(
            conid=contract.conid,
            symbol=contract.symbol,
            sec_type=contract.sec_type,
            exchange=contract.exchange,
            currency=contract.currency,
            setup_family=setup_family,
            reason_stack=("insufficient history to compute this family's rule",),
            liquidity=liquidity,
            volatility=volatility,
            evidence_status="MISSING",
            eligible=True,
            discovered_at=moment,
            scan_cycle_id=cycle_id,
            dedupe_key=dedupe_key,
            queue_state=QueueState.DATA_FAIL,
            freshness_note=freshness_note,
            reject_reason="insufficient history to compute this family's rule",
        )
    else:
        queue_state = QueueState.CANDIDATE if classification.matched else QueueState.WATCH
        candidate = TradingCandidate(
            conid=contract.conid,
            symbol=contract.symbol,
            sec_type=contract.sec_type,
            exchange=contract.exchange,
            currency=contract.currency,
            setup_family=setup_family,
            reason_stack=classification.reason_stack,
            catalyst=catalyst,
            liquidity=liquidity,
            volatility=volatility,
            evidence_status="OK",
            eligible=True,
            discovered_at=moment,
            scan_cycle_id=cycle_id,
            dedupe_key=dedupe_key,
            queue_state=queue_state,
            freshness_note=freshness_note,
            invalidation_reference=classification.invalidation_reference,
        )
    return store.record_candidate(candidate)


def _record_data_fail(
    store: TradingScannerStore, contract: IbkrContract, cycle_id: str, moment: datetime, reason: str
) -> TradingCandidate:
    # No setup_family is meaningful yet (the failure happened before
    # any family could even be evaluated) - recorded once under
    # MOMENTUM_RELATIVE_STRENGTH's own dedupe namespace as the
    # canonical "this contract failed before family evaluation" marker
    # for this cycle, never duplicated per family.
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
