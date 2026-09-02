"""
MarketHunter

Tests for the generic, provider-independent Market Data Evidence
Contract v1: experiment1.models.MarketDataEvidence and
experiment1.market_data_evidence (evaluate_market_data_evidence,
EvidenceGuardedQuoteSource). No provider adapter/credentials involved -
every test uses a fake AsyncEvidenceSource, proving the contract is
genuinely provider-independent.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from experiment1.market_data_evidence import (
    EvidenceGrade,
    EvidenceGuardedQuoteSource,
    evaluate_market_data_evidence,
)
from experiment1.models import (
    AccountKind,
    DecisionAction,
    EvidenceValidationStatus,
    MarketDataEvidence,
    OrderIntent,
    PriceType,
    QuoteMode,
    SessionState,
)

NOW = datetime(2026, 9, 1, 15, 30, tzinfo=timezone.utc)
EXECUTION_MAX_AGE = timedelta(seconds=5)
VALUATION_MAX_AGE = timedelta(hours=24)


def _evidence(**overrides) -> MarketDataEvidence:
    data = dict(
        provider="TEST_PROVIDER",
        instrument="CROX",
        provider_symbol="CROX",
        exchange="XNAS",
        currency="USD",
        price=Decimal("118.50"),
        price_type=PriceType.BID,
        source_timestamp=NOW,
        receive_timestamp=NOW,
        session_state=SessionState.REGULAR,
        mode=QuoteMode.REALTIME,
        source_reference="msg-1",
    )
    data.update(overrides)
    return MarketDataEvidence(**data)


def _intent(symbol="CROX") -> OrderIntent:
    return OrderIntent(
        intent_id="i-1",
        created_at=NOW,
        account=AccountKind.INVESTMENTS_GROWTH,
        action=DecisionAction.BUY,
        symbol=symbol,
        quantity=Decimal("1"),
        reason="test",
    )


class MarketDataEvidenceModelTests(unittest.TestCase):
    def test_a_well_formed_evidence_record_constructs(self):
        _evidence()  # must not raise

    def test_rejects_blank_provider(self):
        with self.assertRaises(ValueError):
            _evidence(provider="  ")

    def test_rejects_blank_instrument(self):
        with self.assertRaises(ValueError):
            _evidence(instrument="")

    def test_rejects_non_positive_price(self):
        with self.assertRaises(ValueError):
            _evidence(price=Decimal("0"))

    def test_rejects_naive_source_timestamp(self):
        with self.assertRaises(ValueError):
            _evidence(source_timestamp=datetime(2026, 9, 1, 15, 30))

    def test_rejects_naive_receive_timestamp(self):
        with self.assertRaises(ValueError):
            _evidence(receive_timestamp=datetime(2026, 9, 1, 15, 30))

    def test_rejects_a_lowercase_currency_code(self):
        with self.assertRaises(ValueError):
            _evidence(currency="usd")

    def test_rejects_a_currency_code_that_is_not_three_letters(self):
        with self.assertRaises(ValueError):
            _evidence(currency="US")


class EvaluateMarketDataEvidenceTests(unittest.TestCase):
    def _evaluate(self, evidence, **overrides):
        kwargs = dict(
            expected_instrument="CROX",
            expected_currency="USD",
            execution_max_age=EXECUTION_MAX_AGE,
            valuation_max_age=VALUATION_MAX_AGE,
            now=NOW,
        )
        kwargs.update(overrides)
        return evaluate_market_data_evidence(evidence, **kwargs)

    # --- valid execution evidence ---------------------------------------

    def test_fresh_realtime_bid_in_regular_session_is_execution_ok(self):
        result = self._evaluate(_evidence())
        self.assertEqual(result.validation_status, EvidenceValidationStatus.VALID)
        self.assertTrue(result.execution_evidence_ok)
        self.assertTrue(result.valuation_evidence_ok)

    def test_trade_and_ask_and_mid_price_types_are_also_execution_eligible(self):
        for price_type in (PriceType.TRADE, PriceType.ASK, PriceType.MID):
            with self.subTest(price_type=price_type):
                result = self._evaluate(_evidence(price_type=price_type))
                self.assertTrue(result.execution_evidence_ok)

    # --- valuation-only evidence (execution_ok False, valuation_ok True) --

    def test_eod_close_is_valuation_ok_but_never_execution_ok(self):
        evidence = _evidence(
            price_type=PriceType.EOD_CLOSE,
            mode=QuoteMode.EOD,
            source_timestamp=NOW - timedelta(hours=2),
        )
        result = self._evaluate(evidence)
        self.assertEqual(result.validation_status, EvidenceValidationStatus.VALID)
        self.assertFalse(result.execution_evidence_ok)
        self.assertTrue(result.valuation_evidence_ok)

    def test_derived_price_is_valuation_ok_but_never_execution_ok(self):
        evidence = _evidence(price_type=PriceType.DERIVED, mode=QuoteMode.DERIVED)
        result = self._evaluate(evidence)
        self.assertFalse(result.execution_evidence_ok)
        self.assertTrue(result.valuation_evidence_ok)

    def test_delayed_mode_is_valuation_ok_but_never_execution_ok(self):
        evidence = _evidence(mode=QuoteMode.DELAYED, source_timestamp=NOW - timedelta(minutes=15))
        result = self._evaluate(evidence)
        self.assertFalse(result.execution_evidence_ok)
        self.assertTrue(result.valuation_evidence_ok)

    def test_outside_regular_session_is_valuation_ok_but_never_execution_ok(self):
        evidence = _evidence(session_state=SessionState.PRE_MARKET)
        result = self._evaluate(evidence)
        self.assertFalse(result.execution_evidence_ok)
        self.assertTrue(result.valuation_evidence_ok)

    def test_realtime_evidence_older_than_execution_bound_but_within_valuation_bound(self):
        evidence = _evidence(source_timestamp=NOW - timedelta(seconds=30))
        result = self._evaluate(evidence)
        self.assertFalse(result.execution_evidence_ok)
        self.assertTrue(result.valuation_evidence_ok)

    # --- stale/missing provenance -----------------------------------------

    def test_missing_evidence_is_missing_and_neither_ok(self):
        result = self._evaluate(None)
        self.assertEqual(result.validation_status, EvidenceValidationStatus.MISSING)
        self.assertFalse(result.execution_evidence_ok)
        self.assertFalse(result.valuation_evidence_ok)

    def test_evidence_older_than_valuation_bound_is_stale_and_neither_ok(self):
        evidence = _evidence(source_timestamp=NOW - timedelta(hours=48))
        result = self._evaluate(evidence)
        self.assertEqual(result.validation_status, EvidenceValidationStatus.STALE)
        self.assertFalse(result.execution_evidence_ok)
        self.assertFalse(result.valuation_evidence_ok)

    def test_a_future_source_timestamp_is_stale_never_trusted(self):
        evidence = _evidence(source_timestamp=NOW + timedelta(minutes=1))
        result = self._evaluate(evidence)
        self.assertEqual(result.validation_status, EvidenceValidationStatus.STALE)
        self.assertFalse(result.execution_evidence_ok)
        self.assertFalse(result.valuation_evidence_ok)

    # --- wrong instrument/currency/listing ----------------------------------

    def test_instrument_mismatch_fails_closed(self):
        evidence = _evidence(instrument="AAPL")
        result = self._evaluate(evidence)
        self.assertEqual(result.validation_status, EvidenceValidationStatus.INSTRUMENT_MISMATCH)
        self.assertFalse(result.execution_evidence_ok)
        self.assertFalse(result.valuation_evidence_ok)

    def test_currency_mismatch_fails_closed(self):
        evidence = _evidence(currency="EUR")
        result = self._evaluate(evidence)
        self.assertEqual(result.validation_status, EvidenceValidationStatus.CURRENCY_MISMATCH)
        self.assertFalse(result.execution_evidence_ok)
        self.assertFalse(result.valuation_evidence_ok)

    def test_listing_mismatch_fails_closed_when_an_expected_exchange_is_given(self):
        evidence = _evidence(exchange="XLON")
        result = self._evaluate(evidence, expected_exchange="XNAS")
        self.assertEqual(result.validation_status, EvidenceValidationStatus.LISTING_MISMATCH)
        self.assertFalse(result.execution_evidence_ok)
        self.assertFalse(result.valuation_evidence_ok)

    def test_no_expected_exchange_means_listing_is_not_checked(self):
        evidence = _evidence(exchange="XLON")
        result = self._evaluate(evidence, expected_exchange=None)
        self.assertEqual(result.validation_status, EvidenceValidationStatus.VALID)


class FakeEvidenceSource:
    """
    A minimal AsyncEvidenceSource - not tied to any real provider,
    proving EvidenceGuardedQuoteSource is genuinely provider-independent.
    """

    def __init__(self, evidence_by_instrument: dict):
        self._evidence_by_instrument = evidence_by_instrument
        self.calls: list[str] = []

    async def evidence_for(self, instrument):
        self.calls.append(instrument)
        return self._evidence_by_instrument.get(instrument)


class EvidenceGuardedQuoteSourceTests(unittest.TestCase):
    def _source(self, evidence_by_instrument, grade, **overrides):
        kwargs = dict(
            expected_currency="USD",
            execution_max_age=EXECUTION_MAX_AGE,
            valuation_max_age=VALUATION_MAX_AGE,
            clock=lambda: NOW,
        )
        kwargs.update(overrides)
        return EvidenceGuardedQuoteSource(FakeEvidenceSource(evidence_by_instrument), grade, **kwargs)

    def test_execution_grade_returns_a_market_quote_for_valid_fresh_evidence(self):
        source = self._source({"CROX": _evidence()}, EvidenceGrade.EXECUTION)
        quote = asyncio.run(source.quote_for(_intent()))
        self.assertIsNotNone(quote)
        self.assertEqual(quote.symbol, "CROX")
        self.assertEqual(quote.price, Decimal("118.50"))
        self.assertEqual(quote.source, "TEST_PROVIDER")
        self.assertEqual(quote.source_reference, "msg-1")

    def test_execution_grade_returns_none_for_an_eod_close(self):
        evidence = _evidence(price_type=PriceType.EOD_CLOSE, mode=QuoteMode.EOD)
        source = self._source({"CROX": evidence}, EvidenceGrade.EXECUTION)
        quote = asyncio.run(source.quote_for(_intent()))
        self.assertIsNone(quote)

    def test_valuation_grade_returns_a_market_quote_for_an_eod_close(self):
        evidence = _evidence(price_type=PriceType.EOD_CLOSE, mode=QuoteMode.EOD, source_timestamp=NOW - timedelta(hours=1))
        source = self._source({"CROX": evidence}, EvidenceGrade.VALUATION)
        quote = asyncio.run(source.quote_for(_intent()))
        self.assertIsNotNone(quote)
        self.assertEqual(quote.price, evidence.price)

    def test_valuation_grade_still_returns_none_for_missing_evidence(self):
        source = self._source({}, EvidenceGrade.VALUATION)
        quote = asyncio.run(source.quote_for(_intent()))
        self.assertIsNone(quote)

    def test_valuation_grade_still_returns_none_for_an_instrument_mismatch(self):
        source = self._source({"CROX": _evidence(instrument="AAPL")}, EvidenceGrade.VALUATION)
        quote = asyncio.run(source.quote_for(_intent()))
        self.assertIsNone(quote)

    def test_never_fabricates_a_quote_for_an_unrecognized_instrument(self):
        source = self._source({}, EvidenceGrade.EXECUTION)
        quote = asyncio.run(source.quote_for(_intent(symbol="UNKNOWN")))
        self.assertIsNone(quote)

    def test_looks_up_evidence_by_the_intents_own_symbol(self):
        fake = FakeEvidenceSource({"CROX": _evidence()})
        source = EvidenceGuardedQuoteSource(
            fake,
            EvidenceGrade.EXECUTION,
            expected_currency="USD",
            execution_max_age=EXECUTION_MAX_AGE,
            valuation_max_age=VALUATION_MAX_AGE,
            clock=lambda: NOW,
        )
        asyncio.run(source.quote_for(_intent(symbol="CROX")))
        self.assertEqual(fake.calls, ["CROX"])

    def test_default_clock_is_the_real_wall_clock_so_fixed_2026_evidence_is_now_stale(self):
        # No clock= injected - production behavior. NOW (2026-09-01) is
        # long past both max_age bounds relative to the real wall
        # clock, so this must fail closed exactly like real stale
        # evidence would - never silently pass using a frozen test time.
        source = EvidenceGuardedQuoteSource(
            FakeEvidenceSource({"CROX": _evidence()}),
            EvidenceGrade.EXECUTION,
            expected_currency="USD",
            execution_max_age=EXECUTION_MAX_AGE,
            valuation_max_age=VALUATION_MAX_AGE,
        )
        quote = asyncio.run(source.quote_for(_intent()))
        self.assertIsNone(quote)

    def test_rejects_a_negative_fee_bps(self):
        with self.assertRaises(ValueError):
            EvidenceGuardedQuoteSource(
                FakeEvidenceSource({}),
                EvidenceGrade.EXECUTION,
                expected_currency="USD",
                execution_max_age=EXECUTION_MAX_AGE,
                valuation_max_age=VALUATION_MAX_AGE,
                fee_bps=Decimal("-1"),
            )


if __name__ == "__main__":
    unittest.main()
