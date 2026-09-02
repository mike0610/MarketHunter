"""
MarketHunter

Behavioral tests for the GIL Trading Scanner v1:
trading_scanner.models/gates/setups/store/scan/universe. No live IBKR
connection anywhere - every test uses a fake AsyncIbkrUniverseSource.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from experiment1.models import SessionState
from trading_scanner.gates import DEFAULT_LIQUIDITY_THRESHOLDS, LiquidityThresholds, evaluate_liquidity_gate
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
from trading_scanner.setups import (
    classify_abnormal_volume_catalyst,
    classify_breakout_or_pullback_in_trend,
    classify_momentum_relative_strength,
)
from trading_scanner.store import TradingScannerError, TradingScannerStore
from trading_scanner.universe import ContractMarketData, build_ibkr_universe_source

NOW = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)


def _contract(conid=1, symbol="AAPL", restricted=False) -> IbkrContract:
    return IbkrContract(conid=conid, symbol=symbol, sec_type="STK", exchange="SMART", currency="USD", restricted=restricted)


def _liquidity(price=Decimal("150"), adv=Decimal("1000000"), addv=Decimal("10000000")) -> LiquidityContext:
    return LiquidityContext(average_daily_volume=adv, average_daily_dollar_volume=addv, last_price=price)


def _rising_closes(n=60, start=Decimal("100")) -> tuple[Decimal, ...]:
    return tuple(start + Decimal(i) for i in range(n))


def _flat_closes(n=60, value=Decimal("100")) -> tuple[Decimal, ...]:
    return tuple(value for _ in range(n))


def _market_data(conid=1, closes=None, volumes=None) -> ContractMarketData:
    closes = closes if closes is not None else _rising_closes()
    volumes = volumes if volumes is not None else tuple(Decimal("1000000") for _ in closes)
    return ContractMarketData(
        conid=conid,
        closes=closes,
        highs=tuple(c + Decimal("1") for c in closes),
        lows=tuple(c - Decimal("1") for c in closes),
        volumes=volumes,
        observed_at=NOW,
    )


def _catalyst(**overrides) -> CatalystEvidence:
    data = dict(description="Q3 earnings beat", source="test-feed", source_reference="ref-1", observed_at=NOW)
    data.update(overrides)
    return CatalystEvidence(**data)


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

    def test_ibkr_contract_restricted_defaults_to_false(self):
        self.assertFalse(_contract().restricted)

    def test_liquidity_context_rejects_a_non_positive_price(self):
        with self.assertRaises(ValueError):
            LiquidityContext(average_daily_volume=Decimal("1"), average_daily_dollar_volume=Decimal("1"), last_price=Decimal("0"))


# --- gates ---------------------------------------------------------------

class LiquidityGateTests(unittest.TestCase):
    def test_a_liquid_regular_session_stock_is_eligible(self):
        result = evaluate_liquidity_gate(_contract(), _liquidity(), SessionState.REGULAR)
        self.assertTrue(result.eligible)

    def test_outside_regular_session_is_ineligible(self):
        result = evaluate_liquidity_gate(_contract(), _liquidity(), SessionState.PRE_MARKET)
        self.assertFalse(result.eligible)
        self.assertTrue(any("session_state" in r for r in result.reasons))

    def test_a_penny_stock_is_ineligible(self):
        result = evaluate_liquidity_gate(_contract(), _liquidity(price=Decimal("2")), SessionState.REGULAR)
        self.assertFalse(result.eligible)
        self.assertTrue(any("last_price" in r for r in result.reasons))

    def test_an_illiquid_symbol_is_ineligible(self):
        result = evaluate_liquidity_gate(_contract(), _liquidity(addv=Decimal("100000")), SessionState.REGULAR)
        self.assertFalse(result.eligible)
        self.assertTrue(any("average_daily_dollar_volume" in r for r in result.reasons))

    def test_a_restricted_contract_is_ineligible_regardless_of_liquidity(self):
        result = evaluate_liquidity_gate(_contract(restricted=True), _liquidity(), SessionState.REGULAR)
        self.assertFalse(result.eligible)
        self.assertTrue(any("restricted" in r for r in result.reasons))

    def test_multiple_failures_are_all_reported_not_just_the_first(self):
        result = evaluate_liquidity_gate(
            _contract(restricted=True), _liquidity(price=Decimal("2"), addv=Decimal("100")), SessionState.CLOSED
        )
        self.assertFalse(result.eligible)
        self.assertEqual(len(result.reasons), 4)

    def test_custom_thresholds_override_the_conservative_defaults(self):
        lenient = LiquidityThresholds(min_last_price=Decimal("1"), min_average_daily_dollar_volume=Decimal("1000"))
        result = evaluate_liquidity_gate(_contract(), _liquidity(price=Decimal("2"), addv=Decimal("2000")), SessionState.REGULAR, lenient)
        self.assertTrue(result.eligible)

    def test_thresholds_must_be_positive(self):
        with self.assertRaises(ValueError):
            LiquidityThresholds(min_last_price=Decimal("0"))

    def test_default_thresholds_constant_matches_the_dataclass_defaults(self):
        self.assertEqual(DEFAULT_LIQUIDITY_THRESHOLDS, LiquidityThresholds())


# --- setups: momentum / relative strength -----------------------------------

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

    def test_without_a_benchmark_behaves_exactly_as_before(self):
        classification = classify_momentum_relative_strength(_market_data(closes=_rising_closes()), benchmark=None)
        self.assertTrue(classification.matched)

    def test_outperforming_the_benchmark_still_matches(self):
        # symbol rises faster than the benchmark over the lookback window.
        symbol = _market_data(conid=1, closes=_rising_closes(start=Decimal("100")))
        weak_benchmark = _market_data(conid=999, closes=_flat_closes())
        classification = classify_momentum_relative_strength(symbol, benchmark=weak_benchmark)
        self.assertTrue(classification.matched)
        self.assertTrue(any("benchmark return" in r for r in classification.reason_stack))

    def test_underperforming_the_benchmark_fails_the_relative_strength_leg(self):
        # symbol rises slowly; benchmark rises much faster over the lookback window.
        slow_symbol_closes = tuple(Decimal("100") + Decimal(i) * Decimal("0.01") for i in range(60))
        symbol = _market_data(conid=1, closes=slow_symbol_closes)
        strong_benchmark = _market_data(conid=999, closes=_rising_closes(start=Decimal("100")))
        classification = classify_momentum_relative_strength(symbol, benchmark=strong_benchmark)
        self.assertFalse(classification.matched)

    def test_a_benchmark_with_insufficient_history_is_ignored_not_a_guess(self):
        symbol = _market_data(conid=1, closes=_rising_closes())
        short_benchmark = _market_data(conid=999, closes=_rising_closes(n=5))
        classification = classify_momentum_relative_strength(symbol, benchmark=short_benchmark)
        # Falls back to the pure trend rule since the benchmark can't be evaluated.
        self.assertTrue(classification.matched)


# --- setups: abnormal volume + catalyst -------------------------------------

class AbnormalVolumeCatalystTests(unittest.TestCase):
    def _volumes(self, spike=False):
        base = [Decimal("1000000")] * 20
        base.append(Decimal("5000000") if spike else Decimal("1000000"))
        return tuple(base)

    def test_a_volume_spike_with_catalyst_matches(self):
        market_data = _market_data(closes=_flat_closes(n=21), volumes=self._volumes(spike=True))
        classification = classify_abnormal_volume_catalyst(market_data, _catalyst())
        self.assertTrue(classification.matched)
        self.assertIn("catalyst", " ".join(classification.reason_stack))

    def test_a_volume_spike_without_catalyst_never_matches(self):
        market_data = _market_data(closes=_flat_closes(n=21), volumes=self._volumes(spike=True))
        classification = classify_abnormal_volume_catalyst(market_data, catalyst=None)
        self.assertFalse(classification.matched)
        self.assertTrue(any("no catalyst" in r for r in classification.reason_stack))

    def test_a_catalyst_without_a_volume_spike_never_matches(self):
        market_data = _market_data(closes=_flat_closes(n=21), volumes=self._volumes(spike=False))
        classification = classify_abnormal_volume_catalyst(market_data, _catalyst())
        self.assertFalse(classification.matched)

    def test_insufficient_history_returns_none(self):
        market_data = _market_data(closes=_flat_closes(n=5), volumes=tuple(Decimal("1") for _ in range(5)))
        classification = classify_abnormal_volume_catalyst(market_data, _catalyst())
        self.assertIsNone(classification)

    def test_never_fabricates_a_catalyst_never_produces_a_partial_fill_style_guess(self):
        # Explicit structural proof: with catalyst=None, no volume ratio,
        # however large, can ever produce matched=True.
        market_data = _market_data(closes=_flat_closes(n=21), volumes=tuple([Decimal("1")] * 20 + [Decimal("999999999")]))
        classification = classify_abnormal_volume_catalyst(market_data, catalyst=None)
        self.assertFalse(classification.matched)


# --- setups: breakout or pullback in trend ----------------------------------

class BreakoutOrPullbackTests(unittest.TestCase):
    def test_a_new_high_in_an_established_trend_is_a_breakout(self):
        closes = _rising_closes(n=60)
        classification = classify_breakout_or_pullback_in_trend(_market_data(closes=closes))
        self.assertTrue(classification.matched)
        self.assertTrue(any("BREAKOUT" in r for r in classification.reason_stack))

    def test_a_shallow_retracement_near_the_sma_is_a_pullback(self):
        # Build a trend, then pull the final close in close to the SMA20 without breaking it.
        closes = list(_rising_closes(n=59))
        sma20 = sum(closes[-20:]) / 20
        closes.append(sma20)  # exactly at the SMA - within the pullback band
        classification = classify_breakout_or_pullback_in_trend(_market_data(closes=tuple(closes)))
        self.assertTrue(classification.matched)
        self.assertTrue(any("PULLBACK" in r for r in classification.reason_stack))

    def test_no_trend_alignment_never_matches(self):
        classification = classify_breakout_or_pullback_in_trend(_market_data(closes=_flat_closes(n=60)))
        self.assertFalse(classification.matched)

    def test_trend_aligned_but_neither_breakout_nor_pullback_does_not_match(self):
        # Rising trend, but the last close is far from both the prior high and the SMA20 band.
        closes = list(_rising_closes(n=60))
        closes[-1] = closes[-2] - Decimal("20")  # well below both the breakout level and the pullback band
        classification = classify_breakout_or_pullback_in_trend(_market_data(closes=tuple(closes)))
        self.assertFalse(classification.matched)

    def test_insufficient_history_returns_none(self):
        classification = classify_breakout_or_pullback_in_trend(_market_data(closes=_rising_closes(n=30)))
        self.assertIsNone(classification)


# --- store -----------------------------------------------------------------

class TradingScannerStoreTests(unittest.TestCase):
    def setUp(self) -> None:
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
        candidate = self._candidate(catalyst=_catalyst())
        self.store.record_candidate(candidate)
        self.assertEqual(self.store.get_candidate(candidate.dedupe_key).catalyst, candidate.catalyst)

    def test_restart_across_a_fresh_store_instance_preserves_candidates(self):
        candidate = self._candidate()
        self.store.record_candidate(candidate)
        second_store = TradingScannerStore(self.store.db_path)
        self.assertEqual(second_store.get_candidate(candidate.dedupe_key), candidate)


# --- scan orchestration ------------------------------------------------------

class FakeUniverseSource:
    def __init__(self, contracts, liquidity_by_conid=None, market_data_by_conid=None, catalyst_by_conid=None):
        self.contracts = contracts
        self.liquidity_by_conid = liquidity_by_conid or {}
        self.market_data_by_conid = market_data_by_conid or {}
        self.catalyst_by_conid = catalyst_by_conid or {}

    async def resolve_universe(self):
        return tuple(self.contracts)

    async def liquidity_context_for(self, contract):
        return self.liquidity_by_conid.get(contract.conid)

    async def market_data_for(self, contract):
        return self.market_data_by_conid.get(contract.conid)

    async def catalyst_for(self, contract):
        return self.catalyst_by_conid.get(contract.conid)


class RunScanCycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TradingScannerStore(Path(self.tmp.name) / "scanner.db")

    def _eligible_source(self, closes=None, volumes=None, catalyst=None):
        contract = _contract()
        closes = closes if closes is not None else _rising_closes()
        return contract, FakeUniverseSource(
            [contract],
            liquidity_by_conid={contract.conid: _liquidity()},
            market_data_by_conid={contract.conid: _market_data(conid=contract.conid, closes=closes, volumes=volumes)},
            catalyst_by_conid={contract.conid: catalyst} if catalyst is not None else {},
        )

    def test_an_eligible_contract_produces_one_row_per_setup_family(self):
        contract, source = self._eligible_source()
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))

        self.assertEqual(result.contracts_seen, 1)
        families = {c.setup_family for c in result.candidates_recorded}
        self.assertEqual(families, set(SetupFamily))
        self.assertEqual(len(result.candidates_recorded), 3)

    def test_a_matching_momentum_setup_is_recorded_as_candidate(self):
        contract, source = self._eligible_source(closes=_rising_closes())
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        momentum = next(c for c in result.candidates_recorded if c.setup_family is SetupFamily.MOMENTUM_RELATIVE_STRENGTH)
        self.assertEqual(momentum.queue_state, QueueState.CANDIDATE)

    def test_a_non_matching_setup_is_recorded_as_watch_never_carries_a_reject_reason(self):
        contract, source = self._eligible_source(closes=_flat_closes())
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        momentum = next(c for c in result.candidates_recorded if c.setup_family is SetupFamily.MOMENTUM_RELATIVE_STRENGTH)
        self.assertEqual(momentum.queue_state, QueueState.WATCH)
        self.assertIsNone(momentum.reject_reason)

    def test_missing_liquidity_context_is_a_single_data_fail_row_not_skipped(self):
        contract = _contract()
        source = FakeUniverseSource([contract])  # no liquidity registered at all
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(len(result.candidates_recorded), 1)
        self.assertEqual(result.candidates_recorded[0].queue_state, QueueState.DATA_FAIL)

    def test_an_illiquid_contract_is_a_single_ineligible_row_not_scored_per_family(self):
        contract = _contract()
        source = FakeUniverseSource([contract], liquidity_by_conid={contract.conid: _liquidity(price=Decimal("1"))})
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(len(result.candidates_recorded), 1)
        self.assertEqual(result.candidates_recorded[0].queue_state, QueueState.INELIGIBLE)

    def test_a_restricted_contract_is_ineligible(self):
        contract = _contract(restricted=True)
        source = FakeUniverseSource([contract], liquidity_by_conid={contract.conid: _liquidity()})
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(result.candidates_recorded[0].queue_state, QueueState.INELIGIBLE)

    def test_missing_market_data_after_eligibility_is_a_single_data_fail_row(self):
        contract = _contract()
        source = FakeUniverseSource([contract], liquidity_by_conid={contract.conid: _liquidity()})
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(len(result.candidates_recorded), 1)
        self.assertEqual(result.candidates_recorded[0].queue_state, QueueState.DATA_FAIL)

    def test_a_volume_catalyst_setup_matches_when_both_conditions_hold(self):
        volumes = tuple([Decimal("1000000")] * 20 + [Decimal("5000000")])
        contract, source = self._eligible_source(closes=_flat_closes(n=21), volumes=volumes, catalyst=_catalyst())
        result = asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        volume_setup = next(c for c in result.candidates_recorded if c.setup_family is SetupFamily.ABNORMAL_VOLUME_CATALYST)
        self.assertEqual(volume_setup.queue_state, QueueState.CANDIDATE)
        self.assertIsNotNone(volume_setup.catalyst)

    def test_rerunning_the_same_cycle_never_duplicates_a_row(self):
        contract, source = self._eligible_source()
        asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        self.assertEqual(len(self.store.list_candidates()), 3)  # one per family, not six

    def test_a_second_distinct_cycle_produces_a_second_set_of_rows(self):
        contract, source = self._eligible_source()
        asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW))
        asyncio.run(run_scan_cycle(source, self.store, scan_cycle_id="cycle-2", now=NOW))
        self.assertEqual(len(self.store.list_candidates()), 6)

    def test_a_benchmark_contract_is_passed_through_to_momentum_only(self):
        contract, source = self._eligible_source(closes=_rising_closes())
        benchmark_contract = _contract(conid=999, symbol="SPY")
        source.market_data_by_conid[999] = _market_data(conid=999, closes=_flat_closes())
        result = asyncio.run(
            run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW, benchmark_contract=benchmark_contract)
        )
        momentum = next(c for c in result.candidates_recorded if c.setup_family is SetupFamily.MOMENTUM_RELATIVE_STRENGTH)
        self.assertTrue(any("benchmark return" in r for r in momentum.reason_stack))

    def test_custom_liquidity_thresholds_are_honored(self):
        contract = _contract()
        source = FakeUniverseSource(
            [contract],
            liquidity_by_conid={contract.conid: _liquidity(price=Decimal("2"), addv=Decimal("2000"))},
            market_data_by_conid={contract.conid: _market_data(conid=contract.conid, closes=_rising_closes())},
        )
        lenient = LiquidityThresholds(min_last_price=Decimal("1"), min_average_daily_dollar_volume=Decimal("1000"))
        result = asyncio.run(
            run_scan_cycle(source, self.store, scan_cycle_id="cycle-1", now=NOW, liquidity_thresholds=lenient)
        )
        self.assertEqual(len(result.candidates_recorded), 3)  # eligible under the lenient thresholds


# --- universe boundary -------------------------------------------------------

class BuildIbkrUniverseSourceTests(unittest.TestCase):
    def test_returns_none_today_never_a_fabricated_live_client(self):
        self.assertIsNone(build_ibkr_universe_source())


if __name__ == "__main__":
    unittest.main()
