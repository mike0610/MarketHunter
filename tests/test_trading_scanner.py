"""
MarketHunter

Behavioral tests for the GIL Trading Scanner v1 bounded slice:
trading_scanner.models/gates/setups/store/scan/universe. No live IBKR
connection anywhere - every test uses a fake AsyncIbkrUniverseSource.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from experiment1.models import SessionState
from trading_scanner.gates import evaluate_liquidity_gate
from trading_scanner.models import (
    CatalystEvidence,
    IbkrContract,
    LiquidityContext,
    QueueState,
    SetupFamily,
    TradingCandidate,
    VolatilityContext,
)
from trading_scanner.scan import run_scan_cycle
from trading_scanner.setups import classify_momentum_relative_strength
from trading_scanner.store import TradingScannerError, TradingScannerStore
from trading_scanner.universe import ContractMarketData, build_ibkr_universe_source

NOW = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)


def _contract(conid=1, symbol="AAPL") -> IbkrContract:
    return IbkrContract(conid=conid, symbol=symbol, sec_type="STK", exchange="SMART", currency="USD")


def _liquidity(price=Decimal("150"), adv=Decimal("1000000"), addv=Decimal("10000000")) -> LiquidityContext:
    return LiquidityContext(average_daily_volume=adv, average_daily_dollar_volume=addv, last_price=price)


def _rising_closes(n=60, start=Decimal("100")) -> tuple[Decimal, ...]:
    return tuple(start + Decimal(i) for i in range(n))


def _flat_closes(n=60, value=Decimal("100")) -> tuple[Decimal, ...]:
    return tuple(value for _ in range(n))


def _market_data(conid=1, closes=None) -> ContractMarketData:
    closes = closes if closes is not None else _rising_closes()
    return ContractMarketData(
        conid=conid,
        closes=closes,
        highs=tuple(c + Decimal("1") for c in closes),
        lows=tuple(c - Decimal("1") for c in closes),
        volumes=tuple(Decimal("1000000") for _ in closes),
        observed_at=NOW,
    )


# --- models ------------------------------------------------------------

class TradingCandidateModelTests(unittest.TestCase):
    def _candidate(self, **overrides) -> TradingCandidate:
        data = dict(
            conid=1,
            symbol="AAPL",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
            setup_family=SetupFamily.MOMENTUM_RELATIVE_STRENGTH,
            reason_stack=("close above SMA20",),
            liquidity=_liquidity(),
            volatility=VolatilityContext(realized_range_pct=Decimal("3.5")),
            evidence_status="OK",
            eligible=True,
            discovered_at=NOW,
            scan_cycle_id="cycle-1",
            dedupe_key="1:MOMENTUM_RELATIVE_STRENGTH:cycle-1",
            queue_state=QueueState.CANDIDATE,
        )
        data.update(overrides)
        return TradingCandidate(**data)

    def test_a_well_formed_candidate_constructs(self):
        self._candidate()

    def test_requires_a_non_empty_reason_stack(self):
        with self.assertRaises(ValueError):
            self._candidate(reason_stack=())

    def test_rejected_states_require_a_reject_reason(self):
        with self.assertRaises(ValueError):
            self._candidate(queue_state=QueueState.REJECTED, reject_reason=None)

    def test_candidate_watch_states_must_not_carry_a_reject_reason(self):
        with self.assertRaises(ValueError):
            self._candidate(queue_state=QueueState.CANDIDATE, reject_reason="should not be here")

    def test_rejected_state_with_reason_constructs(self):
        self._candidate(queue_state=QueueState.REJECTED, reject_reason="thesis stale")

    def test_ibkr_contract_rejects_a_non_positive_conid(self):
        with self.assertRaises(ValueError):
            IbkrContract(conid=0, symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD")

    def test_liquidity_context_rejects_a_non_positive_price(self):
        with self.assertRaises(ValueError):
            LiquidityContext(average_daily_volume=Decimal("1"), average_daily_dollar_volume=Decimal("1"), last_price=Decimal("0"))


# --- gates ---------------------------------------------------------------

class LiquidityGateTests(unittest.TestCase):
    def test_a_liquid_regular_session_stock_is_eligible(self):
        result = evaluate_liquidity_gate(_liquidity(), SessionState.REGULAR)
        self.assertTrue(result.eligible)

    def test_outside_regular_session_is_ineligible(self):
        result = evaluate_liquidity_gate(_liquidity(), SessionState.PRE_MARKET)
        self.assertFalse(result.eligible)
        self.assertTrue(any("session_state" in r for r in result.reasons))

    def test_a_penny_stock_is_ineligible(self):
        result = evaluate_liquidity_gate(_liquidity(price=Decimal("2")), SessionState.REGULAR)
        self.assertFalse(result.eligible)
        self.assertTrue(any("last_price" in r for r in result.reasons))

    def test_an_illiquid_symbol_is_ineligible(self):
        result = evaluate_liquidity_gate(_liquidity(addv=Decimal("100000")), SessionState.REGULAR)
        self.assertFalse(result.eligible)
        self.assertTrue(any("average_daily_dollar_volume" in r for r in result.reasons))

    def test_multiple_failures_are_all_reported_not_just_the_first(self):
        result = evaluate_liquidity_gate(_liquidity(price=Decimal("2"), addv=Decimal("100")), SessionState.CLOSED)
        self.assertFalse(result.eligible)
        self.assertEqual(len(result.reasons), 3)


# --- setups ----------------------------------------------------------------

class MomentumRelativeStrengthTests(unittest.TestCase):
    def test_a_rising_series_matches(self):
        classification = classify_momentum_relative_strength(_market_data(closes=_rising_closes()))
        self.assertTrue(classification.matched)
        self.assertIsNotNone(classification.invalidation_reference)

    def test_a_flat_series_does_not_match(self):
        classification = classify_momentum_relative_strength(_market_data(closes=_flat_closes()))
        self.assertFalse(classification.matched)
        self.assertIsNone(classification.invalidation_reference)

    def test_a_falling_series_does_not_match(self):
        falling = tuple(Decimal("200") - Decimal(i) for i in range(60))
        classification = classify_momentum_relative_strength(_market_data(closes=falling))
        self.assertFalse(classification.matched)

    def test_insufficient_history_returns_none_not_a_guess(self):
        classification = classify_momentum_relative_strength(_market_data(closes=_rising_closes(n=30)))
        self.assertIsNone(classification)

    def test_reason_stack_is_never_empty_either_way(self):
        matched = classify_momentum_relative_strength(_market_data(closes=_rising_closes()))
        unmatched = classify_momentum_relative_strength(_market_data(closes=_flat_closes()))
        self.assertTrue(matched.reason_stack)
        self.assertTrue(unmatched.reason_stack)


# --- store -----------------------------------------------------------------

class TradingScannerStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TradingScannerStore(Path(self.tmp.name) / "scanner.db")

    def _candidate(self, **overrides) -> TradingCandidate:
        data = dict(
            conid=1,
            symbol="AAPL",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
            setup_family=SetupFamily.MOMENTUM_RELATIVE_STRENGTH,
            reason_stack=("close above SMA20",),
            liquidity=_liquidity(),
            volatility=VolatilityContext(realized_range_pct=Decimal("3.5")),
            evidence_status="OK",
            eligible=True,
            discovered_at=NOW,
            scan_cycle_id="cycle-1",
            dedupe_key="1:MOMENTUM_RELATIVE_STRENGTH:cycle-1",
            queue_state=QueueState.CANDIDATE,
        )
        data.update(overrides)
        return TradingCandidate(**data)

    def test_record_and_read_back_a_candidate(self):
        candidate = self._candidate()
        self.store.record_candidate(candidate)
        self.assertEqual(self.store.get_candidate(candidate.dedupe_key), candidate)

    def test_identical_resubmission_is_idempotent(self):
        candidate = self._candidate()
        self.store.record_candidate(candidate)
        self.store.record_candidate(candidate)  # no raise
        self.assertEqual(len(self.store.list_candidates()), 1)

    def test_same_dedupe_key_different_content_raises(self):
        self.store.record_candidate(self._candidate())
        with self.assertRaises(TradingScannerError):
            self.store.record_candidate(self._candidate(symbol="MSFT"))

    def test_list_candidates_filters_by_queue_state(self):
        self.store.record_candidate(self._candidate(dedupe_key="k1", queue_state=QueueState.CANDIDATE))
        self.store.record_candidate(
            self._candidate(dedupe_key="k2", queue_state=QueueState.REJECTED, reject_reason="stale")
        )
        candidates = self.store.list_candidates(queue_state=QueueState.CANDIDATE)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].dedupe_key, "k1")

    def test_a_candidate_with_catalyst_round_trips(self):
        candidate = self._candidate(
            catalyst=CatalystEvidence(
                description="Q3 earnings beat", source="test-feed", source_reference="ref-1", observed_at=NOW
            )
        )
        self.store.record_candidate(candidate)
        self.assertEqual(self.store.get_candidate(candidate.dedupe_key).catalyst, candidate.catalyst)

    def test_restart_across_a_fresh_store_instance_preserves_candidates(self):
        candidate = self._candidate()
        self.store.record_candidate(candidate)
        second_store = TradingScannerStore(self.store.db_path)
        self.assertEqual(second_store.get_candidate(candidate.dedupe_key), candidate)


# --- scan orchestration ------------------------------------------------------

class FakeUniverseSource:
    def __init__(self, contracts, liquidity_by_conid=None, market_data_by_conid=None):
        self.contracts = contracts
        self.liquidity_by_conid = liquidity_by_conid or {}
        self.market_data_by_conid = market_data_by_conid or {}

    async def resolve_universe(self):
        return tuple(self.contracts)

    async def liquidity_context_for(self, contract):
        return self.liquidity_by_conid.get(contract.conid)

    async def market_data_for(self, contract):
        return self.market_data_by_conid.get(contract.conid)


class RunScanCycleTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TradingScannerStore(Path(self.tmp.name) / "scanner.db")

    def test_a_matching_contract_is_recorded_as_candidate(self):
        contract = _contract()
        source = FakeUniverseSource(
            [contract],
            liquidity_by_conid={contract.conid: _liquidity()},
            market_data_by_conid={contract.conid: _market_data(conid=contract.conid, closes=_rising_closes())},
        )
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))

        self.assertEqual(result.contracts_seen, 1)
        self.assertEqual(len(result.candidates_recorded), 1)
        self.assertEqual(result.candidates_recorded[0].queue_state, QueueState.CANDIDATE)

    def test_a_non_matching_contract_is_recorded_as_watch(self):
        contract = _contract()
        source = FakeUniverseSource(
            [contract],
            liquidity_by_conid={contract.conid: _liquidity()},
            market_data_by_conid={contract.conid: _market_data(conid=contract.conid, closes=_flat_closes())},
        )
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(result.candidates_recorded[0].queue_state, QueueState.WATCH)

    def test_missing_liquidity_context_is_data_fail_not_skipped(self):
        contract = _contract()
        source = FakeUniverseSource([contract])  # no liquidity registered at all
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(result.candidates_recorded[0].queue_state, QueueState.DATA_FAIL)

    def test_an_illiquid_contract_is_ineligible_not_scored(self):
        contract = _contract()
        source = FakeUniverseSource(
            [contract], liquidity_by_conid={contract.conid: _liquidity(price=Decimal("1"))}
        )
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(result.candidates_recorded[0].queue_state, QueueState.INELIGIBLE)

    def test_missing_market_data_after_eligibility_is_data_fail(self):
        contract = _contract()
        source = FakeUniverseSource([contract], liquidity_by_conid={contract.conid: _liquidity()})
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(result.candidates_recorded[0].queue_state, QueueState.DATA_FAIL)

    def test_rerunning_the_same_cycle_never_duplicates_a_row(self):
        contract = _contract()
        source = FakeUniverseSource(
            [contract],
            liquidity_by_conid={contract.conid: _liquidity()},
            market_data_by_conid={contract.conid: _market_data(conid=contract.conid, closes=_rising_closes())},
        )
        asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(len(self.store.list_candidates()), 1)

    def test_a_second_distinct_cycle_produces_a_second_row(self):
        contract = _contract()
        source = FakeUniverseSource(
            [contract],
            liquidity_by_conid={contract.conid: _liquidity()},
            market_data_by_conid={contract.conid: _market_data(conid=contract.conid, closes=_rising_closes())},
        )
        asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-2", now=NOW))
        self.assertEqual(len(self.store.list_candidates()), 2)

    def test_multiple_contracts_are_each_recorded_independently(self):
        c1, c2 = _contract(conid=1, symbol="AAPL"), _contract(conid=2, symbol="MSFT")
        source = FakeUniverseSource(
            [c1, c2],
            liquidity_by_conid={1: _liquidity(), 2: _liquidity()},
            market_data_by_conid={
                1: _market_data(conid=1, closes=_rising_closes()),
                2: _market_data(conid=2, closes=_flat_closes()),
            },
        )
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(result.contracts_seen, 2)
        states = {c.symbol: c.queue_state for c in result.candidates_recorded}
        self.assertEqual(states["AAPL"], QueueState.CANDIDATE)
        self.assertEqual(states["MSFT"], QueueState.WATCH)


# --- universe boundary -------------------------------------------------------

class BuildIbkrUniverseSourceTests(unittest.TestCase):
    def test_returns_none_today_never_a_fabricated_live_client(self):
        self.assertIsNone(build_ibkr_universe_source())


if __name__ == "__main__":
    unittest.main()
